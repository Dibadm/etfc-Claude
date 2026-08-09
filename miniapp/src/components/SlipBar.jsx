export default function SlipBar({ count, onOpen }) {
  return (
    <button className="slip-bar" onClick={onOpen}>
      <span className="slip-bar__count">{count}</span>
      {count === 1 ? "Selection" : `Selections — Parlay`}
      <span className="slip-bar__arrow">Review →</span>
    </button>
  );
}
