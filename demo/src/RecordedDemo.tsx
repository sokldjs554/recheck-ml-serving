const media = `${import.meta.env.BASE_URL}media/`;

export default function RecordedDemo() {
  return (
    <details className="recorded-demo" data-testid="recorded-demo">
      <summary>실제 실행 영상</summary>
      <p id="recorded-demo-scope">
        현재 UI를 로컬 Python API·SQLite에 연결해 촬영한 저장된 시연입니다. 현재 요청의 진행 상황과는 별개입니다.
      </p>
      <video
        controls
        preload="none"
        playsInline
        poster={`${media}recheck-records-final-poster-20261019.webp`}
        aria-label="저장된 실제 API 시연"
        aria-describedby="recorded-demo-scope"
      >
        <source src={`${media}recheck-records-final-20261019.mp4`} type="video/mp4" />
        <source src={`${media}recheck-records-final-20261019.webm`} type="video/webm" />
        <a href={`${media}recheck-records-final-20261019.mp4`}>시연 영상 열기</a>
      </video>
      <p>
        원문 변경 → 이전 답변 차단 → 최신 답변 기록 → 동일 작업 반환.
        기록되지 않은 답변, 실제 저장된 답변 한 건, 재시도 후 유지된 동일 기록을 보여줍니다.
      </p>
    </details>
  );
}
