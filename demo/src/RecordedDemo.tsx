const media = `${import.meta.env.BASE_URL}media/`;

export default function RecordedDemo() {
  return (
    <details className="recorded-demo" data-testid="recorded-demo">
      <summary>이전 실행 영상</summary>
      <p id="recorded-demo-scope">
        이전 화면을 로컬 Python API·SQLite에서 촬영한 실제 시연입니다. 현재 화면과 배치·문구가 다릅니다. 현재 요청의 진행 상황은 실행 화면에서 확인하세요.
      </p>
      <video
        controls
        preload="none"
        playsInline
        poster={`${media}recheck-poster.webp`}
        aria-label="저장된 실제 API 시연"
        aria-describedby="recorded-demo-scope"
      >
        <source src={`${media}recheck-walkthrough.mp4`} type="video/mp4" />
        <source src={`${media}recheck-walkthrough.webm`} type="video/webm" />
        <a href={`${media}recheck-walkthrough.mp4`}>시연 영상 열기</a>
      </video>
      <p>
        300만 원 답변 → 한도 변경 → 이전 답변 차단 → 새 답변 기록 → 같은 작업 ID
        재확인. 화면을 옮겨도 실행 결과는 유지됩니다.
      </p>
    </details>
  );
}
