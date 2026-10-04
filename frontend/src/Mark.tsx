export default function Mark() {
  return (
    <span className="mark">
      <svg viewBox="0 0 32 32" width="30" height="30" aria-hidden="true">
        <path d="M10.5 9l-6.5 7 6.5 7M21.5 9l6.5 7-6.5 7" className="mark-brackets" />
        <path d="M18.6 6.5l-5.2 19" className="mark-slash" />
      </svg>
      Ohara
    </span>
  );
}
