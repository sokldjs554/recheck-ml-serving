const media = `${import.meta.env.BASE_URL}media/`;

export default function RecordedDemo() {
  return (
    <details className="recorded-demo" data-testid="recorded-demo">
      <summary>실제 실행 영상</summary>
      <p id="recorded-demo-scope">
        현재 UI를 로컬 Python API·SQLite에 연결해 촬영한 저장된 시연입니다. 현재 요청의 진행 상황과는 별개입니다. 모델 부하·장애 복구 화면은 과거 실험 자료입니다.
      </p>
      <video
        controls
        preload="none"
        playsInline
        poster={`${media}recheck-workspace-poster-20261019.webp`}
        aria-label="저장된 실제 API 시연"
        aria-describedby="recorded-demo-scope"
      >
        <source src={`${media}recheck-workspace-20261019.mp4`} type="video/mp4" />
        <source src={`${media}recheck-workspace-20261019.webm`} type="video/webm" />
        <a href={`${media}recheck-workspace-20261019.mp4`}>시연 영상 열기</a>
      </video>
      <p>
        원문 변경 → 이전 답변 차단 → 최신 답변 기록 → 동일 작업 반환.
        이어서 결제 취소 문서의 직접 기록·조회와 별도 모델 부하·장애 복구 근거를 확인합니다.
      </p>
    </details>
  );
}
