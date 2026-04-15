import { useMemo, useState } from "react";
import "./styles.css";

const API_BASE = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8010").replace(/\/$/, "");

function toResults(payload) {
  if (Array.isArray(payload)) return { results: payload, breakdownById: {} };
  const results = Array.isArray(payload?.results) ? payload.results : [];
  const breakdown = Array.isArray(payload?.breakdown) ? payload.breakdown : [];
  const breakdownById = {};
  for (const row of breakdown) {
    const id = String(row?.id || "").trim();
    if (!id) continue;
    breakdownById[id] = row;
  }
  return { results, breakdownById };
}

function App() {
  const [query, setQuery] = useState("");
  const [debugMode, setDebugMode] = useState(false);
  const [results, setResults] = useState([]);
  const [breakdownById, setBreakdownById] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const canSearch = query.trim().length > 0;

  async function onSearch(event) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    setLoading(true);
    setError("");
    try {
      const url = debugMode ? `${API_BASE}/ai/recommend?debug=true` : `${API_BASE}/ai/recommend`;
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmed }),
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      const payload = await res.json();
      const parsed = toResults(payload);
      setResults(parsed.results);
      setBreakdownById(parsed.breakdownById);
    } catch (err) {
      setResults([]);
      setBreakdownById({});
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  const displayRows = useMemo(() => {
    return results.map((item, index) => {
      const id = String(item?.id || "").trim();
      return {
        id,
        title: String(item?.title || id || `Result ${index + 1}`),
        date: String(item?.date || item?.start_date || ""),
        description: String(item?.description || item?.reason || "").slice(0, 160),
      };
    });
  }, [results]);

  async function onCardClick(id) {
    if (!id) return;
    const activeQuery = query.trim();
    try {
      await fetch(`${API_BASE}/ai/click`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: activeQuery,
          clicked_id: id,
        }),
      });
    } catch {
      // Ignore click tracking failure in thin test UI.
    }
  }

  return (
    <div className="page">
      <h1>What should I do?</h1>
      <form className="search-row" onSubmit={onSearch}>
        <input
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Type a query..."
        />
        <button type="submit" disabled={!canSearch || loading}>
          Search
        </button>
      </form>
      <label className="debug-toggle">
        <input type="checkbox" checked={debugMode} onChange={(event) => setDebugMode(event.target.checked)} />
        Debug mode
      </label>

      {loading ? <p>Loading...</p> : null}
      {error ? <p className="error">{error}</p> : null}

      <div className="results">
        {displayRows.map((item) => {
          const debugRow = breakdownById[item.id];
          const comp = debugRow?.components || {};
          return (
            <button key={item.id || item.title} className="card" type="button" onClick={() => onCardClick(item.id)}>
              <h2>{item.title || "Untitled"}</h2>
              {item.date ? <p className="meta">{item.date}</p> : null}
              {item.description ? <p>{item.description}</p> : <p className="meta">No description</p>}
              {debugMode && debugRow ? (
                <pre className="debug">
{`Score: ${Number(debugRow.final_score || 0).toFixed(2)}
base: ${Number(comp.base || 0).toFixed(2)}
click: ${Number(comp.click || 0).toFixed(2)}
popularity: ${Number(comp.popularity || 0).toFixed(2)}
recency: ${Number(comp.recency || 0).toFixed(2)}
semantic: ${Number(comp.semantic || 0).toFixed(2)}`}
                </pre>
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default App;
