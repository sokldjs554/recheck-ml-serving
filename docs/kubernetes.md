# Kubernetes 운영 실험

RECHECK의 실제 Python API, 모델 HTTP 서비스, PostgreSQL을 격리된 `kind-recheck-ops` 클러스터에서 실행한다. API와 모델은 각각 2개 replica이며 PostgreSQL은 PVC를 사용하는 단일 StatefulSet이다. **모든 Pod와 제어 평면은 같은 물리 호스트를 공유한다. 운영 환경 HA, DB failover, 장기간 가용성을 증명하는 실험이 아니다.**

## 실제 실행 결과 — 2026-10-08 UTC

[GitHub Actions 실행 37806017582](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/37806017582), commit `b602512533b6a15f0dbcf2cfcc2b9b2ca3b1fa21`에서 **6개 운영 검증이 통과했다.** 16:07:50 이후부터 16:10:16까지 수집한 291개 요청 표본 중 289개가 `clear`, 2개가 HTTP 오류였다. 오류 2개는 모두 단일 PostgreSQL Pod 교체 단계에서 관측되었다.

| 단계 | 표본 | clear | HTTP 오류 |
| --- | ---: | ---: | ---: |
| 정상 상태 | 10 | 10 | 0 |
| API Pod 교체 | 30 | 30 | 0 |
| 모델 Pod 교체 | 26 | 26 | 0 |
| 순차 rolling restart | 92 | 92 | 0 |
| readiness 실패 rollout | 47 | 47 | 0 |
| rollback | 6 | 6 | 0 |
| PostgreSQL Pod 교체 | 70 | 68 | 2 |
| 복구 후 | 10 | 10 | 0 |

첫 두 실패 표본의 시작 시각은 `16:10:06.903950`, `16:10:07.404088` UTC다. 요약 로그만으로 정확한 downtime은 계산하지 않는다. [기계 판독 요약](evidence/kubernetes-ci-summary.json)과 [원시 JSON/명령 로그 artifact](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/37806017582/artifacts/11562883319)를 함께 제공한다. 로컬 클라우드 실행기는 디스크 부족으로 HTTP 검증에 도달하지 못했으며 [별도 실패 기록](evidence/kubernetes-local-attempt.json)에 남겼다. 성공 수치는 GitHub의 별도 일회성 runner에서 얻은 값이다.

[두 번째 실행 37806785360](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/37806785360), commit `73f5fcde21f7c32cd4c27dd80ca375a4cd413cce`도 6개 검증과 3개 성공 판정 negative control을 통과했다. 287개 표본 중 283개 `clear`, PostgreSQL 교체 중 HTTP 오류 4개였으며 나머지 단계에서는 HTTP 오류나 `review`를 관측하지 않았다. [반복 실행 요약](evidence/kubernetes-ci-repeat.json)과 [원시 artifact](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/37806785360/artifacts/11562429881)를 보관한다. 두 실행의 오류 수가 다르다는 사실도 단일 DB의 짧은 교체 중단을 0초 가용성으로 표현할 수 없는 이유다.

## 재현

Docker, Python 3, `kind v0.27.0`, `kubectl v1.32.2`가 필요하다. 바이너리는 PATH 또는 `work/tools/`에 둔다.

```bash
bash scripts/k8s_lab.sh
```

스크립트는 전용 kubeconfig(`work/kubernetes/kubeconfig`)를 사용하며 기존 `recheck-ops` 클러스터가 있으면 중단한다. 다른 클러스터의 기본 context를 바꾸지 않는다. HTTP는 `127.0.0.1:18080`에만 노출한다. 결과는 `docs/evidence/kubernetes-proof.json`과 `.log`에 저장한다. JSON에 전체 HTTP 표본, 실험별 오류 수, 연속 실패 이후 최초 복구 표본까지의 관측 시간, 명령 결과, 실제 receipt와 각 replica의 동일 idempotency key 재생 결과가 포함된다.

```bash
# 실험 전용 클러스터 삭제. PVC 데이터도 함께 사라진다.
KUBECONFIG="$PWD/work/kubernetes/kubeconfig" work/tools/kind delete cluster --name recheck-ops
```

[CI workflow](../.github/workflows/kubernetes.yml)는 동일 스크립트를 실행하고 원시 결과를 artifact로 보관한다. CI를 구성했다는 사실과 실제 CI 실행 성공은 구분해야 한다. 별도 실행 링크/상태 없이 원격 CI 성공을 주장하지 않는다.

## 검증 내용

1. PostgreSQL 준비 후 schema-init Job으로 최초 테이블 생성을 직렬화하고 API/model을 각각 2개 띄운다.
2. 실제 protected inference의 `clear` 상태와 model hash, trace ID를 확인한다. 동일 idempotency key를 **각 API Pod에 직접** 보내도 같은 receipt ID가 반환되는지 확인한다.
3. API와 모델 Pod를 각각 삭제해 새 UID의 Pod로 대체되는지 확인한다.
4. 두 Deployment를 순차 rolling restart한다. `maxUnavailable: 0`, `maxSurge: 1`, `minReadySeconds: 5`를 적용한다.
5. 모델 신규 revision의 readiness 경로를 고의로 잘못 지정한다. rollout이 제한 시간 내 성공하지 않고 기존 2개 replica가 가용한지 확인한 뒤 `rollout undo`로 복구한다. **모델 정확도/모델 파일 손상 실험이 아니라 readiness 실패 차단 실험**이다.
6. PostgreSQL Pod를 삭제하고 같은 PVC UID로 재생성되는지, 기존 immutable receipt ID/hash가 그대로 남는지 확인한다. 오래된 receipt의 freshness가 계속 유효하다는 주장은 하지 않는다.

각 단계 이후 새 session에서 새 protected inference가 `clear`이고 즉시 validate 결과가 `valid: true`여야 성공한다. HTTP 200 응답만으로 정상 추론이라고 판단하지 않는다. 모니터는 0.5초 간격을 목표로 session 생성과 추론을 실제 실행하며 HTTP 오류와 HTTP 200의 `review` 결과를 따로 기록한다. 연속 요청 방식이므로 느린 응답 동안 표본 간격이 길어질 수 있다. 실패 표본이 없다는 것은 정확히 0초 downtime을 증명하지 않는다.

## 장애 경계와 설정

- `/live`: 프로세스 자체의 회복 불가능한 상태를 검사한다. API의 DB/모델 장애 때문에 모든 API를 재시작하지 않는다.
- `/ready`: API는 DB `SELECT 1`과 모델 준비 상태/hash를 확인한다. 모델은 준비된 모델 및 실행기 상태를 확인한다. 준비되지 않은 Pod는 Service endpoint에서 빠진다.
- API/model 각각 CPU request 100m, limit 1 CPU, memory request 128Mi, limit 512Mi. PostgreSQL도 동일 한도로 설정했다. 이 값은 용량 산정 결과가 아니라 작은 실험 환경의 제한값이다.
- API/model PDB `minAvailable: 1`은 eviction API를 통한 자발적 중단에 적용된다. 직접 Pod 삭제나 호스트 장애를 막지 않으며 이 실험은 PDB eviction 동작 자체를 검증하지 않는다.
- 종료 시 5초 preStop으로 endpoint 전파 시간을 주고 Uvicorn graceful shutdown 20초, Pod termination grace 30초를 사용한다. 이를 모든 네트워크 상황에서의 무손실 종료 보장으로 해석하지 않는다.
- 단일 PostgreSQL 교체 중 오류가 발생할 수 있다. PVC는 Pod 교체에 대한 보존이며 호스트/디스크 장애나 클러스터 삭제를 견디는 백업이 아니다.
- 비밀번호는 격리된 로컬 실험용 고정 값이다. 외부 배포에는 별도 secret 관리, TLS, 백업/복구, DB HA 구성이 필요하다.

## 중첩 컨테이너 실행 환경

이 클라우드 실행기는 중첩 overlayfs와 IPv6 iptables를 지원하지 않았다. 전용 IPv4 Docker bridge와 containerd `native` snapshotter를 사용했다. `/dev/kmsg`가 없어 해당 node에 `/dev/null`을 읽기 전용으로 연결했으므로 커널 로그 기반 OOM 관찰은 사용할 수 없다. 컨테이너 종료 상태/리소스 지표는 별개다.

`native`는 레이어를 복사하므로 32GB 디스크에서 일반 다중 레이어 이미지로 먼저 실행했을 때 공간이 소진되었다. 최종 스크립트는 **실험용** API 이미지와 PostgreSQL 이미지를 `docker export/import`로 한 레이어로 만들며 실행 user, working directory, 필수 환경변수와 entrypoint를 유지한다. 실제 운영 배포 Dockerfile은 변경하지 않는다. `RECHECK_K8S_SKIP_BUILD=1`은 이미 준비한 로컬 실험 이미지 재사용용이며 기본/CI 실행은 현재 소스를 빌드한다.

초기 실패 시도와 최종 검증의 실행 이미지는 결과 파일과 런타임 기록을 함께 참고한다. 전체 Docker prune은 사용하지 않는다. 자동 승인 검토가 활성 node의 광범위 snapshot 삭제를 위험하다고 거절하여, 그 방식 대신 실험 전용 클러스터를 삭제하고 다시 생성했다.
