# RECHECK를 위한 Python 추론 서버 소스·성능 심층 감사

조사일: 2026-10-17. **외부 프로젝트 4개의 구현, 실제 테스트 코드, 벤치마크 생성·집계 코드를 읽은 정적 감사다. 외부 테스트나 부하를 이번 조사에서 실행하지 않았다.** README의 주장, 소스로 확인한 동작, 아직 재현하지 않은 위험을 구분했다. 화면·데모 조사는 별도 담당 범위다. 본 문서에 채용 합격 사례나 은행 운영 실적 주장은 없다.

## 먼저 바뀌어야 할 비교 결론

1. **BentoML의 adaptive batching을 bounded admission과 같은 기능으로 묶으면 틀린다.** 배처 자체는 길이 상한 없는 deque이고, 별도 HTTP concurrency middleware가 429를 낸다. batch latency 예측도 전체 요청에 대한 엄격한 마감 보장이 아니다.
2. **MLServer의 worker 재시작은 실패 요청의 durable replay가 아니다.** 해당 worker의 진행 중 future를 WorkerStop으로 실패시키고 새 프로세스에 모델을 다시 로드한다. 반면 작은 비교 프로젝트는 Redis Streams의 pending entry를 회수한다. “worker recovery”라는 동일 표현이 서로 다른 계약이다.
3. **“MLServer 1,100/1,500 RPS”는 이번에 찾은 코드에서는 CI 통과 기준이다.** 실제 측정 결과가 아니다. 게다가 상태 검사에 실패율 threshold가 없으므로 rate만으로 정상 추론 처리량을 보장하지 않는다.
4. **작은 프로젝트의 p95 250ms는 200ms 간격 polling을 포함한 결과 관측 지연이다.** RECHECK의 동기 응답 지연과 나란히 놓고 빠르기를 평가하면 안 된다.
5. **RECHECK에는 이미 참고 사례보다 분명한 좋은 계약이 있다.** CPU 작업을 HTTP 취소 이후에도 수용 슬롯에 계속 계상하는 코드와 테스트, 예정 도착 시점부터의 지연·유효 결과 처리량, PostgreSQL 대사가 있다. 새 프레임워크를 도입하는 것보다 이 계약을 쉽게 검증 가능하게 보여주는 쪽의 이득이 크다.

## 고정한 조사 버전

| 프로젝트 | 읽은 commit | 선택 이유 |
|---|---|---|
| BentoML | `517b343b81aeb0b01bbd908e58e53ad9c12ef7eb` | adaptive batching의 실제 시간 예산과 admission 경계 |
| Ray Serve | `f178b1887d2f9bb43a323678dc54c14aae7378be` | queue limit, 취소 전파, timeout·streaming 테스트 |
| MLServer | `a325e523b5a580d49aeb06e19e73e4a90176b63b` | 프로세스 pool 실패, batch queue, benchmark CI |
| kevin-sparkflow/ml-inference-service | `c200bcb4721c4428a9bfe808ca8a61648a2b16f6` | 작은 Python gateway/worker에서 lease·fencing·원본 부하 기록을 함께 읽을 수 있음 |

관측한 commit에 고정했으며 안정 릴리스라고 주장하지 않는다. 특히 Ray의 최신 개발 브랜치 동작을 이전 릴리스에 소급하면 안 된다. 파일별 URL·행 수·함수 위치는 같은 디렉터리의 `sources.json`에 37개를 기록했다.

## 1. BentoML: “배치로 처리량 개선” 뒤의 실제 한계

### 요청 경로와 수용 제한

`ServiceAppFactory`가 batchable API마다 `CorkDispatcher`를 만들고, fallback은 `ServiceUnavailable("process is overloaded")`를 발생시킨다. service의 max_concurrency는 worker 수로 나눈 뒤 올림하여 worker별 상한으로 전달한다. 따라서 service 전체에 하나의 원자적인 글로벌 counter가 있는 구조로 설명하면 안 된다. 나눗셈이 맞아떨어지지 않으면 worker 상한의 합이 설정 숫자보다 커질 수도 있다. [서비스 조립 코드](https://github.com/bentoml/BentoML/blob/517b343b81aeb0b01bbd908e58e53ad9c12ef7eb/src/_bentoml_impl/server/app.py)

`MaxConcurrencyMiddleware`는 semaphore가 잠겨 있으면 기다리는 대신 HTTP429로 반환한다. metrics/health/live/ready 경로는 기본 제외다. 이것은 **HTTP 요청 admission**이다. 한편 dispatcher의 `_queue`는 `collections.deque()`이며 소스에 maxlen TODO가 남아 있다. 배치 한 번의 최대 크기와 대기 요청 수 상한은 서로 다르다. [HTTP traffic middleware](https://github.com/bentoml/BentoML/blob/517b343b81aeb0b01bbd908e58e53ad9c12ef7eb/src/bentoml/_internal/server/http/traffic.py), [CorkDispatcher](https://github.com/bentoml/BentoML/blob/517b343b81aeb0b01bbd908e58e53ad9c12ef7eb/src/bentoml/_internal/marshal/dispatcher.py)

### 지연 예산·취소

dispatcher는 최근 최대 50개 outbound 관측값으로 배치 크기와 소요 시간의 선형 관계를 추정한다. 기본 semaphore는 한 번에 한 batch만 처리한다. 오래 기다렸고 예측 지연이 예산을 넘는 요청의 future를 취소하여 fallback으로 보낸다. 그러나 모델 실행을 강제 중단하는 hard real-time deadline은 아니다. 초기 학습 동안 필요한 표본을 확보하려고 일부 deadline 취소를 보수적으로 처리하며, 이미 실행한 callback은 끝날 수 있다. 타이밍도 `time.time()` 기반이다. 따라서 “max_latency_ms 이하를 모든 요청에서 보장”이라는 표현은 이 코드만으로 입증되지 않는다. [src/bentoml/_internal/marshal/dispatcher.py](https://github.com/bentoml/BentoML/blob/517b343b81aeb0b01bbd908e58e53ad9c12ef7eb/src/bentoml/_internal/marshal/dispatcher.py)

`TimeoutMiddleware`의 waiter는 **첫 ASGI send**에서 완료된다. 첫 send 전에 제한을 넘으면 app task를 cancel하고 504를 반환한다. 첫 send 이후에는 app future의 종료를 기다리므로, 이것을 전체 streaming 응답의 종료 deadline이라고 부르면 안 된다. threadpool의 동기 모델 연산을 task cancel로 즉시 중단한다는 근거도 없다. [src/bentoml/_internal/server/http/traffic.py](https://github.com/bentoml/BentoML/blob/517b343b81aeb0b01bbd908e58e53ad9c12ef7eb/src/bentoml/_internal/server/http/traffic.py)

### 실제 읽은 테스트와 그 증거의 범위

| 테스트 | 확인하는 주장 | 이 테스트가 증명하지 않는 것 |
|---|---|---|
| `test_serve_with_timeout` | timeout 설정에서 echo_delay 호출이 오류가 됨 | CPU 연산 강제 종료, 취소 이후 자원 회수 시점 |
| `test_serve_with_api_max_concurrency` | api worker 1개에서 두 요청을 실행 중 세 번째 요청이 Too many requests로 실패 | 여러 worker에 걸친 엄격한 전역 상한 |
| `test_serve_with_lifecycle_hooks` | worker 4개 startup/shutdown hook 및 deployment hook 횟수 | 진행 중 작업의 durable recovery |

출처: [tests/e2e/bento_server_http/tests/test_serve.py](https://github.com/bentoml/BentoML/blob/517b343b81aeb0b01bbd908e58e53ad9c12ef7eb/tests/e2e/bento_server_http/tests/test_serve.py). 테스트 파일을 읽었고 이번에 실행하지 않았다. repository tree와 검색을 확인했지만 dispatcher 특화 단위 테스트는 이번 범위에서 찾지 못했다. “테스트가 없다”는 전체 저장소 단정으로 확대하지 않는다.

### 성능·비용·RECHECK 적용

공식 설명은 여러 worker가 모델 복사본을 각각 메모리에 올린다고 명시한다. batching 이득은 모델의 vectorization과 입력 형태에 달렸으며, worker 개수만 늘려도 성능이 선형 증가한다고 볼 수 없다. [docs/source/build-with-bentoml/parallelize-requests.rst](https://github.com/bentoml/BentoML/blob/517b343b81aeb0b01bbd908e58e53ad9c12ef7eb/docs/source/build-with-bentoml/parallelize-requests.rst)

내부 benchmark 도구는 성공·실패 지연을 나누고 client busy 비율로 부하 발생기의 건강성을 경고한다. 그러나 도구 코드 자체가 특정 모델·하드웨어의 결과는 아니다. 별도 benchmark repository로 이동했다는 링크는 이번 GitHub 연결에서 404여서 처리량 숫자를 차용하지 않았다. [src/bentoml/_internal/utils/benchmark.py](https://github.com/bentoml/BentoML/blob/517b343b81aeb0b01bbd908e58e53ad9c12ef7eb/src/bentoml/_internal/utils/benchmark.py)

**RECHECK 판단:** 현 CPU-ensemble은 요청 내부에서 이미 4,096개 scenario를 처리한다. 외부 요청을 다시 배치했을 때 이득이 있는지, 배치 대기로 300ms 예산을 침해하는지 별도 실험이 필요하다. 배치 도입을 기본 개선안으로 삼지 않는다. 화면에는 “실행 2 / 대기 최대 4 / 합계 6”처럼 현재 admission 계약을 먼저 보여주는 것이 낫다.

## 2. Ray Serve: queue와 취소를 테스트로 설명하는 방식

### admission과 취소가 코드에서 만나는 지점

`RouterMetricsManager.wrap_request_assignment`는 현재 queue 수와 `max_queued_requests`를 비교하여 `BackPressureError`를 발생시킨다. `-1`이면 제한하지 않는다. `wrap_queued_request`는 finally에서 counter를 감소시켜 assign 이전 취소도 정리한다. 이 한도는 router/handle의 관측 단위이지 모든 클러스터 호출자의 공유 queue counter가 아니다. 소스에는 async routing 시 실제 필요보다 많은 요청을 거절할 수 있다는 설명도 있다. [python/ray/serve/_private/router.py](https://github.com/ray-project/ray/blob/f178b1887d2f9bb43a323678dc54c14aae7378be/python/ray/serve/_private/router.py)

이번 commit의 test는 기본 503, 선택적 429와 Retry-After=7 두 경우를 확인한다. 이전 비교 문서의 “Ray=503”은 기본값 설명으로 한정해야 한다. `max_ongoing_requests=1`, `max_queued_requests=1`을 쓰고 SignalActor로 첫 요청을 실제로 멈춘 뒤 두 번째를 대기시키고 후속 요청 10개를 거절시키는 구조다. sleep만으로 부하가 발생했다고 가정하는 것보다 재현 의도가 명확하다. [python/ray/serve/tests/test_backpressure.py](https://github.com/ray-project/ray/blob/f178b1887d2f9bb43a323678dc54c14aae7378be/python/ray/serve/tests/test_backpressure.py)

HTTP disconnect 또는 timeout이 나면 assign 전 요청은 버리고, replica에 넘어간 작업은 asyncio task 취소를 시도한다. cancel은 다음 await 지점에서 관측된다. await 없는 긴 동기 계산은 끝나고 결과가 버려질 수 있다. downstream deployment/task/actor로 취소가 전파되며, DeploymentHandle 호출에 shield를 씌우는 것만으로 downstream 취소를 막지 못한다. [doc/source/serve/http-guide.md](https://github.com/ray-project/ray/blob/f178b1887d2f9bb43a323678dc54c14aae7378be/doc/source/serve/http-guide.md)

### 실제 읽은 timeout 테스트

| 테스트 | 검증하는 관측값 |
|---|---|
| `test_request_hangs_in_assignment` | 진행 중·대기 중 요청 모두 408, 해제 후 새 요청 200 |
| `test_cancel_on_http_timeout_during_assignment` | timeout 난 queued request는 replica 호출 횟수에 추가되지 않음 |
| `test_cancel_on_http_timeout_during_execution` | FastAPI 유무 두 경우에서 ingress와 downstream 모두 cancellation signal 관측 |
| `test_request_timeout_does_not_leak_tasks` | timeout 10회 이후 RUNNING actor task 수가 원래 0으로 돌아옴 |
| `test_streaming_request_already_sent_and_timed_out` | 첫 chunk 200을 받은 뒤 timeout 나면 다음 chunk 읽기가 protocol error로 끝남 |

출처: [python/ray/serve/tests/test_request_timeout.py](https://github.com/ray-project/ray/blob/f178b1887d2f9bb43a323678dc54c14aae7378be/python/ray/serve/tests/test_request_timeout.py). **이미 response header가 나간 streaming 요청은 뒤늦게 408이라는 새 HTTP status로 바꿀 수 없다.** 성공 코드와 실제 완결 여부를 따로 세어야 하는 이유를 잘 보여준다.

### 장애 복구와 비용

공식 fault-tolerance 문서는 health-check 실패 replica를 kill/restart하고, worker node의 actor를 다른 healthy node에서 다시 띄우는 동작을 설명한다. 기본 head node는 단일 장애점이며 GCS fault tolerance에는 외부 Redis 등이 필요하다. controller가 죽은 동안 autoscaling과 replica health checking이 동작하지 않는다는 경계도 있다. 이것을 “프레임워크 도입만으로 end-to-end exactly-once 보장”으로 해석하지 않는다. [doc/source/serve/production-guide/fault-tolerance.md](https://github.com/ray-project/ray/blob/f178b1887d2f9bb43a323678dc54c14aae7378be/doc/source/serve/production-guide/fault-tolerance.md)

현재 개발 문서에는 요청별 header로 timeout 및 disconnect 감지를 끄는 fast path도 나온다. 속도 수치를 비교할 때 취소 감시 계약을 같게 맞추지 않으면 공정하지 않다. [doc/source/serve/advanced-guides/performance.md](https://github.com/ray-project/ray/blob/f178b1887d2f9bb43a323678dc54c14aae7378be/doc/source/serve/advanced-guides/performance.md)

### benchmark 소스가 실제로 측정하는 것

`http_noop_latency.py`의 기본값은 replica 1개, 측정 요청 100개다. common 함수는 warmup 100개를 제외하고 요청을 **직렬** 실행하며 perf_counter로 wall latency를 기록한다. Noop 모델은 빈 byte를 반환한다. 이는 framework/HTTP overhead microbenchmark이지 복잡한 CPU model serving goodput가 아니다. CPU 기종·quota·RSS·측정 실행 결과는 이 코드에 없다. [python/ray/serve/_private/benchmarks/http_noop_latency.py](https://github.com/ray-project/ray/blob/f178b1887d2f9bb43a323678dc54c14aae7378be/python/ray/serve/_private/benchmarks/http_noop_latency.py), [python/ray/serve/_private/benchmarks/common.py](https://github.com/ray-project/ray/blob/f178b1887d2f9bb43a323678dc54c14aae7378be/python/ray/serve/_private/benchmarks/common.py)

common throughput helper는 기본 trial 10개 × trial_runtime 1초, 초기 warmup 0.1초이고 실제 경과 시간으로 throughput을 계산한다. HTTP batch helper에는 connection error를 잡고도 latency를 반환하는 경로가 있으므로, 반환 latency 배열만 정상 응답률의 분모로 사용하면 안 된다. 사용한 benchmark wrapper의 실패 집계까지 읽어야 한다.

**RECHECK 판단:** Ray cluster를 붙이는 것은 현재 문제보다 운영 범위를 크게 늘린다. 가져올 것은 테스트의 구체성이다. “timeout 처리 지원” 대신 **queued timeout은 worker 미진입 / CPU 시작 후 timeout은 슬롯 유지 / drain 후 슬롯 0** 세 관측값을 한 요청 수명으로 제시하자. Ray의 408을 따라 기존 504를 변경할 필요는 없다. API 계약의 일관성이 중요하다.

## 3. MLServer: pool 회복과 accepted job 회복을 분리해야 한다

### parallel worker의 실제 동작

`InferencePool`은 multiprocessing worker와 response queue를 만들고 모델 registry를 보관한다. worker가 비정상 종료하면 dispatcher에서 제거하고 해당 worker의 in-flight future에 `WorkerStop(exit_code)`를 넣는다. 새 worker를 띄우고 등록 모델을 다시 load한 뒤 routing에 복귀시킨다. 기존 요청을 새 worker에 자동 재제출하는 로직은 읽은 경로에 없다. [mlserver/parallel/pool.py](https://github.com/SeldonIO/MLServer/blob/a325e523b5a580d49aeb06e19e73e4a90176b63b/mlserver/parallel/pool.py), [mlserver/parallel/dispatcher.py](https://github.com/SeldonIO/MLServer/blob/a325e523b5a580d49aeb06e19e73e4a90176b63b/mlserver/parallel/dispatcher.py)

worker의 requests/model_updates는 별도 multiprocessing Queue이며 maxsize를 전달하지 않는다. worker는 request를 읽어 async task로 schedule한다. 이 구조를 “parallel_workers 개수만큼만 요청을 받아 전체 queue가 bounded”라고 설명하면 안 된다. [mlserver/parallel/worker.py](https://github.com/SeldonIO/MLServer/blob/a325e523b5a580d49aeb06e19e73e4a90176b63b/mlserver/parallel/worker.py)

batcher는 `Queue(maxsize=max_batch_size)`를 쓰지만 full일 때 `await put`로 기다린다. semaphore로 전체 inbound coroutines 수를 cap하거나 즉시 overload reject하는 계약과 다르다. 완성한 batch는 task로 즉시 schedule하여 여러 batch를 동시에 처리할 수 있다. `max_batch_time`은 **batch 구성 대기 시간**이며 IPC·inference·network까지의 전체 deadline이 아니다. [mlserver/batching/adaptive.py](https://github.com/SeldonIO/MLServer/blob/a325e523b5a580d49aeb06e19e73e4a90176b63b/mlserver/batching/adaptive.py)

### 정적 검토에서 드러난 확인 과제

dispatcher `_wait`는 취소/종료 시 finally에서 future map을 지운다. response loop의 resolve는 message id로 map을 바로 조회한다. batcher도 response 기다림 종료 시 map을 지우고 callback이 id로 map을 조회한다. **취소 후 늦게 도착한 응답의 lookup 경로를 추가 검토할 가치가 있다.** 이것은 소스에서 확인한 테스트 후보이지 재현된 장애로 단정하지 않는다. 외부 caller가 실제로 언제 cancel하는지까지 연결한 실행 검증은 하지 않았다.

### 실제 읽은 테스트

- `tests/parallel/test_pool.py::test_on_worker_stop`: 이전 PID가 사라지고 설정한 worker 수를 유지.
- `test_start_worker`: 새 worker startup 동안 모델 predict 결과를 계속 확인.
- `test_start_worker_new_model`: 새 worker 시작과 새 모델 load가 겹쳐도 모델을 호출할 수 있음.
- `tests/parallel/test_dispatcher.py::test_cancel`: worker 종료에 따른 future 실패와 exit code 확인. **HTTP client disconnect 테스트가 아니다.**
- `tests/batching/test_adaptive.py::test_batch_requests_timeout`: batch가 꽉 차지 않아도 시간 경과 후 batch를 방출.
- `test_batcher_propagates_errors`, `test_batcher_cancels_responses`: 모델·batcher 오류를 대기 응답에 전달.

출처: [tests/parallel/test_pool.py](https://github.com/SeldonIO/MLServer/blob/a325e523b5a580d49aeb06e19e73e4a90176b63b/tests/parallel/test_pool.py), [tests/parallel/test_dispatcher.py](https://github.com/SeldonIO/MLServer/blob/a325e523b5a580d49aeb06e19e73e4a90176b63b/tests/parallel/test_dispatcher.py), [tests/batching/test_adaptive.py](https://github.com/SeldonIO/MLServer/blob/a325e523b5a580d49aeb06e19e73e4a90176b63b/tests/batching/test_adaptive.py). 어느 테스트도 이번 조사에서 실행하지 않았다.

### CI benchmark 해부

| 항목 | 코드로 확인한 조건 |
|---|---|
| runner | GitHub Actions ubuntu-latest; 정확한 CPU 모델·할당량 미기록 |
| 언어/도구 | Python3.10, k6 0.44.1 |
| server | worker 2개, metrics_endpoint=null, localhost |
| model/input | sklearn runtime의 iris, metadata [1,4] FP32 |
| batching | 최대 300 requests, max_batch_time 0.3초 |
| workload | REST와 gRPC 각각 constant-vus 300, 60초 |
| 준비 | server 시작 뒤 고정 sleep5; setup에서 model load |
| threshold | REST http_reqs rate>1100; gRPC custom counter rate>1500 |
| latency | k6 기본 latency 관측은 가능하나 scenario에 p95/p99 SLO threshold 없음 |
| 오류 | 상태 check는 있지만 checks 성공률 또는 http_req_failed threshold가 scenario에 없음 |
| 실제 결과 | 이번에 대응 run 결과·원본 latency distribution 확보하지 않음 |

근거: [benchmark workflow](https://github.com/SeldonIO/MLServer/blob/a325e523b5a580d49aeb06e19e73e4a90176b63b/.github/workflows/benchmark.yml), [REST scenario](https://github.com/SeldonIO/MLServer/blob/a325e523b5a580d49aeb06e19e73e4a90176b63b/benchmarking/scenarios/inference-rest.js), [gRPC scenario](https://github.com/SeldonIO/MLServer/blob/a325e523b5a580d49aeb06e19e73e4a90176b63b/benchmarking/scenarios/inference-grpc.js), [server 설정](https://github.com/SeldonIO/MLServer/blob/a325e523b5a580d49aeb06e19e73e4a90176b63b/benchmarking/testserver/settings.json), [iris 설정](https://github.com/SeldonIO/MLServer/blob/a325e523b5a580d49aeb06e19e73e4a90176b63b/benchmarking/testserver/models/iris/model-settings.json).

gRPC counter는 status check 결과와 관계없이 checkResponse에서 1을 증가시킨다. REST http_reqs도 정상 추론만의 전용 counter가 아니다. 따라서 **threshold 숫자를 “성공 처리량”으로 변환하는 것은 근거 없는 주장**이다. [benchmarking/common/rest.js](https://github.com/SeldonIO/MLServer/blob/a325e523b5a580d49aeb06e19e73e4a90176b63b/benchmarking/common/rest.js), [benchmarking/common/grpc.js](https://github.com/SeldonIO/MLServer/blob/a325e523b5a580d49aeb06e19e73e4a90176b63b/benchmarking/common/grpc.js)

**RECHECK 판단:** 외부 사례를 본 뒤에도 HTTP200이지만 deferred인 응답을 goodput에서 제외하는 현재 기준을 유지해야 한다. MLServer가 잘 다루는 multi-model runtime·V2 protocol은 현 제품에 필요가 생기기 전에는 범위를 넓힐 이유가 약하다. 반면 worker 재시작 중 readiness와 모델 load 경쟁을 다루는 테스트 형태는 유용한 후속 참고다.

## 4. 작은 Python 사례: ml-inference-service를 끝까지 읽었을 때

### 구조보다 중요한 delivery 계약

gateway는 sync FastAPI endpoint여서 Redis·upload read를 threadpool에서 실행한다. enqueue는 Redis WATCH/MULTI/EXEC로 stream 길이 검사, job hash 생성, TTL, XADD를 묶고 contention은 최대 8회 재시도한다. full 또는 반복 contention은 503이고 실패 job record를 남기지 않도록 설계했다. stream entry를 완료 시 삭제하기 때문에 길이는 queued와 in-flight를 함께 포함한다. [src/inference_service/gateway/app.py](https://github.com/kevin-sparkflow/ml-inference-service/blob/c200bcb4721c4428a9bfe808ca8a61648a2b16f6/src/inference_service/gateway/app.py)

worker는 XAUTOCLAIM으로 오래된 pending delivery를 회수한다. **결과 publish·ack·delete는 Lua 안에서 XPENDING의 현재 owner가 자신인지 확인한 뒤 원자적으로 수행한다.** 오래된 worker가 뒤늦게 완료해도 새 owner의 결과를 덮지 못한다. XAUTOCLAIM cursor도 유지하여 앞쪽 healthy entry 때문에 뒤의 abandoned job이 계속 굶는 것을 피한다. [src/inference_service/worker/queue.py](https://github.com/kevin-sparkflow/ml-inference-service/blob/c200bcb4721c4428a9bfe808ca8a61648a2b16f6/src/inference_service/worker/queue.py)

이것은 exactly-once inference가 아니다. lease보다 오래 실행하면 같은 모델 연산을 다시 할 수 있다. 공개 설명의 기본 lease는 30초이고, 처리 시작 때 payload/result TTL을 갱신한다. Redis Streams와 hash는 durable database transaction 그 자체가 아니며 Compose는 단일 Redis + AOF everysec다. host crash 시 마지막 약1초 쓰기를 잃을 수 있다는 경계를 README가 인정한다. [README.md](https://github.com/kevin-sparkflow/ml-inference-service/blob/c200bcb4721c4428a9bfe808ca8a61648a2b16f6/README.md), [docker-compose.yml](https://github.com/kevin-sparkflow/ml-inference-service/blob/c200bcb4721c4428a9bfe808ca8a61648a2b16f6/docker-compose.yml)

POST202 이후 client가 나가도 job은 계속 진행하는 설계이며 cancel API나 요청별 execution deadline은 읽은 endpoint에 없다. Locust의 30초는 **클라이언트 관찰 종료 시한**이다. 그 시간이 지나면 서버가 자동 취소된다고 보면 안 된다.

### 테스트는 무엇을 잡는가

| 테스트 | 주입 상황·assert |
|---|---|
| `test_concurrent_admission_never_exceeds_capacity` | barrier로16 submissions 동시 시작, cap3, 정확히3개 accept, 거절 job key 없음 |
| `test_slow_redis_submission_does_not_block_event_loop` | Redis xlen block 중 OpenAPI async endpoint가 응답 |
| `test_worker_recovers_job_interrupted_after_delivery` | fake Redis에서 idle을60초로 만들어 replacement reclaim, done 및 stream/pending 정리 |
| `test_stale_worker_cannot_publish_or_ack_replacement_work` | old owner update가 false; 새 결과 이후에도 overwrite 실패 |
| `test_result_write_outage_leaves_job_recoverable` | done publication에 ConnectionError, payload 남음, 재회수 후 완료 |
| `test_expired_payload_is_acknowledged_without_recreating_job` | payload 소실 시 새 job을 꾸며 만들지 않고 stream 정리 |
| `test_inflight_jobs_still_count_toward_capacity` | 이미 delivery된 pending job도 cap 점유 |

근거: [tests/test_gateway_concurrency.py](https://github.com/kevin-sparkflow/ml-inference-service/blob/c200bcb4721c4428a9bfe808ca8a61648a2b16f6/tests/test_gateway_concurrency.py), [tests/test_worker_recovery.py](https://github.com/kevin-sparkflow/ml-inference-service/blob/c200bcb4721c4428a9bfe808ca8a61648a2b16f6/tests/test_worker_recovery.py). 이들은 fakeredis+stub classifier 기반이다. README의 real Redis/SIGKILL runtime check 서술은 별도 저자 주장이고 여기 표의 unit test와 혼동하지 않는다.

### 공개 성능 숫자와 조건

| 항목 | 저자가 공개한 값·코드 확인 |
|---|---|
| machine | Windows의 Docker, CPU worker2. **CPU 모델·물리코어·cgroup quota·RAM 미공개** |
| 모델 | MobileNetV2 ONNX, CPU. exact model bytes/hash와 runtime version은 본 표에 검증해 넣지 못함 |
| 입력 | 랜덤 단색 320×240 PNG. 정확도나 자연 이미지 분포 대표성 없음 |
| load | Locust user20, spawn5/s, 60초, think0.5–1.5초, result polling0.2초, stop-timeout35 |
| 결과 | submit852, e2e852, poll1696, 보고 실패0 |
| submit latency | p50 6ms, p95 23ms |
| e2e latency | p50 220ms, p95 250ms, p99 280ms, 최대411ms |
| 정의 | image 생성 전 perf_counter부터 submit와 queue·inference·polling 및 결과 관측 완료까지 |
| 반복·warmup | 별도 반복 run 분산·전용 warmup 구간 확인 못함 |
| 독립 재현 | 하지 않음 |

근거: [README.md](https://github.com/kevin-sparkflow/ml-inference-service/blob/c200bcb4721c4428a9bfe808ca8a61648a2b16f6/README.md), [loadtest/locustfile.py](https://github.com/kevin-sparkflow/ml-inference-service/blob/c200bcb4721c4428a9bfe808ca8a61648a2b16f6/loadtest/locustfile.py), [benchmarks/2026-09-10.txt](https://github.com/kevin-sparkflow/ml-inference-service/blob/c200bcb4721c4428a9bfe808ca8a61648a2b16f6/benchmarks/2026-09-10.txt).

중요한 해석 세 가지: (1) 20 users는 동시에20 inference를 뜻하지 않는다. 대부분 think/poll 대기일 수 있다. (2) 로그의 Aggregated 62.97 req/s는 submit+poll+합성 E2E event가 섞인 값이므로 jobs/s로 쓸 수 없다. (3) 개별 e2e/submit rate15.78/s와 총852를 단순60초로 나눈 값은 같지 않다. 원본에 실제 집계 window timestamp가 없어 그 차이를 추측으로 확정하지 않는다. 이 결과를 최대 capacity로 부르지 않는다.

**RECHECK 판단:** 이 프로젝트의 좋은 점은 작은 범위에서 admission·owner fencing·중복 실행 허용·보존 기간의 경계를 명시한다는 것이다. 그러나 Redis Streams를 RECHECK에 넣으면 기존 동기 /decisions + PostgreSQL receipt 계약이 job polling 계약으로 변한다. 현재 제품 문제에 맞지 않으므로 복사할 기능이 아니라 **“어느 실패를 복구하며 어느 실패는 보장하지 않는가”를 쓰는 방식**을 가져오는 것이 맞다.

## 5. RECHECK 현재 코드에 대조한 평가

읽은 로컬 기준: `/workspace/work/recheck-review`. 기존 실행 산출물을 읽었으며 이번 조사에서 다시 실행하지 않았다.

| 항목 | 외부에서 얻은 질문 | RECHECK 코드에서 실제 확인 | 판단 |
|---|---|---|---|
| bounded admission | semaphore만인지, 대기까지 cap인지 | `admission.py`: concurrency+queue cap, check/increment 사이 await 없음, finally counter 해제 | 이미 명확한 강점. 단일 프로세스 event loop 범위임을 명시 |
| timeout 이후 CPU | 응답이 끝나면 실제 compute도 끝나는가 | `worker.py`: compute task 전체 shield, cpu_started 뒤에는 task 취소 안 하고 슬롯 유지 | 현재 동작을 지워 “빠른 취소”처럼 만들면 악화 |
| worker failure | 요청 replay인가 pool repair인가 | `execution.py`: BrokenProcessPool 감지, `worker.py` ready/health/live503 | supervisor restart 필요. MLServer 내부 재시작과 다른 선택 |
| test evidence | 말뿐인 cancellation인가 | `tests/test_compute.py`: 취소 후 active1·후속429·drain후0; child.kill 후ready503 | 외부 참고표보다 이 직접 증거를 앞에 놓을 가치 |
| 모델 비용 | 실제 무거운 연산인가 | `model.py`: ExtraTrees128, depth12, n_jobs1; 4096 scenario 평균과 point score 혼합 | synthetic robustness workload이며 실제 금융 모델 비용으로 일반화 금지 |
| useful throughput | HTTP200을 모두 성공으로 세는가 | `benchmark_fullpath_sustained.py`: useful reason + scheduled-arrival latency<=deadline | 외부 simple rate보다 결과 의미가 분명 |
| DB 일관성 | 전달 결과와 저장 결과가 맞는가 | 동일 script에서 receipt key·payload 대사, response tail·worker drain 구분 | 유지할 차별점. inference framework가 대신 제공하지 않음 |

### 기존 180초 실험을 읽을 때의 정확한 문장

`docs/evidence/fullpath-sustained-summary.json`은 2026-10-12 측정분이다. real HTTP API → HTTP CPU process pool → localhost PostgreSQL의 **/decisions 경로**이고 상담 evidence execution이 아니다. Linux shared host, affinity CPU0–4, model worker2, worker queue4, gateway concurrency8/queue8, DB pool4, session32, deadline300ms 조건이다. 정확한 CPU 모델·유효 CPU quota는 이 summary에 없어 별도 확인이 필요하다.

첫 overload30초 구간: target120/s, 3,600시도, 유효 기한 내 결과2,032(56.44%), deferred1,477, HTTP429 91. 유효 응답 scheduled p95는199.34ms다. 모든 응답 p95 185.09ms가 더 낮은 것은 빠르게 거절/보류된 요청이 섞여 있기 때문이다. **“120 RPS 처리, p95 185ms”만 쓰면 의미를 왜곡한다.**

두 번째 overload30초: 3,600시도, 유효2,040(56.67%), deferred1,506,429 53,504 1. 회복 판단은 연속한5초 arrival window 두 개에서 good>=99%, sent>=목표95%, scheduled p95<=150ms, sample queue<=1, probe error 없음이다. “즉시 회복” 대신 최초 구간 안정 관측 및10초 확인이라고 설명해야 한다.

자원 측정은 API/model process tree만이고 PostgreSQL·generator는 제외한다. RSS 합은 shared page를 중복 계산할 수 있다. 외부 framework의 전체 cluster cost 또는 cloud billing과 직접 비교하지 않는다. 보고서가 이미 이 경계를 기록한 것은 유지해야 할 장점이다.

## 6. 성능 비교를 다시 만들 경우의 최소 실험 설계

아래는 **제안이며 미실행**이다. 현재 승인 범위는 조사이므로 코드를 수정하지 않았다.

1. **같은 계산을 먼저 고정:** 동일 exported artifact/hash, 동일 features corpus, 동일 worker수·CPU quota·memory limit·thread 환경. 작은 MobileNet/Iris/noop 숫자로 RECHECK 우열을 만들지 않는다.
2. **3층으로 따로 측정:** model 함수 단독 / HTTP inference worker / gateway+worker+PostgreSQL. 모델 시간이 전체 응답의 어느 비율인지 제시한다.
3. **한꺼번에 바꾸지 않기:** 현재 bounded process baseline, batch 적용 실험, 필요한 경우 대표 framework1개만 adapter로 비교. batch1/작은batch/큰batch에서 대기 예산과 memory를 함께 기록.
4. **open-loop arrival 사용:** low→saturation→recovery, due/send/complete timestamp, generator lag, warmup·steady·drain 구분. closed-loop user수만으로 capacity를 주장하지 않는다.
5. **같은 서비스 계약:** deadline, HTTP timeout, 취소 후 CPU 점유, queue cap, retry, metrics, DB commit을 같게 맞춘다. Ray fast path처럼 감시를 끈 결과는 별도 변형으로 표시한다.
6. **분모 보존:** 모든 offered attempt, actual send, HTTP outcome, useful-on-time, useful-late, deferred, refused, client/server timeout, cancellation. successful p95와 all-outcome p95를 각각.
7. **실패 시나리오도 결과로:** queued deadline, running CPU timeout, caller disconnect, child kill, response lost after commit, stale lease publication. 한 번에 한 장애로 로그·trace·counter·DB row를 연결.
8. **한 실행 결과를 원본까지:** config+artifact+source hash+host metadata+raw events+summary 생성 script. 두세 번의 반복 분산과 전체 resource accounting이 없으면 “개선 확정” 대신 관측 결과로 표시.

## 7. 화면에 들어갈 가치가 있는 증거

- **요청 한 건의 수명:** accepted → queued → CPU started → HTTP timeout → CPU finished → slot released. “응답 종료”와 “실제 연산 종료”의 시각을 두 개로 그린다.
- **부하 chart의 분모:** offered/sent/useful/deferred/rejected를 같은30초 window에서 확인하고, 선택한 window의 raw request id로 내려간다. MLServer CI처럼 rate만 크게 보이는 화면을 만들지 않는다.
- **복구 증거:** child PID와 readiness failure, supervisor restart, 새 readiness, 후속 요청 성공을 연결한다. 현재 저장된 증거가 어디까지인지 먼저 확인하고 없는 단계는 미검증으로 표시.
- **학습한 선택:** Bento의 batching, Ray의 cluster, MLServer의 runtime, Redis Streams의 job delivery를 넣지 않은 이유를 실제 비용과 현재 필요로 설명한다. “기술을 안 썼다”가 아니라 현재 계약을 지키는 최소 구성이라는 근거가 있어야 한다.

## 조사 한계와 남은 확인

4개 프로젝트의 전체 저장소 감사나 보안 검토는 아니다. 특정 파일·테스트·benchmark를 심층으로 확인한 결과다. 표의 기능은 이번 정적 관찰 범위다. 특히 Bento worker crash의 supervisor 세부와 Ray actor failure 시 이미 실행된 사용자 부작용은 이번에 실행으로 검증하지 않았다. MLServer cancellation 후 late response 경로는 의심 지점이며 확인된 버그라고 부르지 않는다.

외부 결과 중 CPU·할당량·모델 artifact·latency 정의가 모두 갖춰져 RECHECK와 직접 비교 가능한 benchmark는 이번 범위에서 확보하지 못했다. 이 결론은 숫자를 모으지 못했다는 빈칸이 아니라, 원본 benchmark와 counter 정의까지 읽고 **비교 가능한 숫자인지 판별한 결과**다.
