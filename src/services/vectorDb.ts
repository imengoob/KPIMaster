/**
 * Lightweight in-memory vector database using TF-IDF bag-of-words embeddings
 * and cosine similarity search. No external ML models required.
 *
 * Architecture:
 *   1. Tokenise every record's text into terms.
 *   2. Build a shared vocabulary and compute IDF across the corpus.
 *   3. Represent every document as a sparse TF-IDF vector.
 *   4. At query time: embed the query the same way → cosine similarity → top-K.
 */

// ── Stop-words to ignore ──────────────────────────────────────────────────────

const STOP_WORDS = new Set([
  "a","an","the","and","or","but","in","on","at","to","for","of","with","by",
  "from","is","are","was","were","be","been","being","have","has","had",
  "do","does","did","will","would","could","should","may","might","shall",
  "i","me","my","we","our","you","your","he","his","she","her","it","its",
  "they","them","their","this","that","these","those","what","which","who",
  "how","when","where","why","all","each","every","some","any","no","not",
  "show","tell","give","get","find","list","many","much","more","most",
]);

// ── Types ─────────────────────────────────────────────────────────────────────

export type RecordType = "ticket" | "blocker" | "developer" | "sprint" | "kpi" | "action";

export interface VectorRecord {
  id:       string;
  type:     RecordType;
  text:     string;       // human-readable text used for embedding
  metadata: Record<string, unknown>;  // original data passed through to RAG
}

interface IndexedRecord extends VectorRecord {
  vector: number[];       // TF-IDF vector (dense, vocabulary-aligned)
  norm:   number;         // pre-computed ||v|| for fast cosine
}

export interface SearchResult {
  record: VectorRecord;
  score:  number;        // cosine similarity 0..1
}

// ── Tokeniser ─────────────────────────────────────────────────────────────────

function tokenise(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter(t => t.length > 1 && !STOP_WORDS.has(t));
}

function termFrequency(tokens: string[]): Map<string, number> {
  const tf = new Map<string, number>();
  for (const t of tokens) tf.set(t, (tf.get(t) ?? 0) + 1 / tokens.length);
  return tf;
}

// ── VectorDB class ────────────────────────────────────────────────────────────

class VectorDB {
  private corpus:  IndexedRecord[] = [];
  private vocab:   Map<string, number> = new Map();  // term → column index
  private idf:     number[] = [];                     // column → IDF weight
  private dirty    = false;

  // ── Ingestion ───────────────────────────────────────────────────────────────

  add(record: VectorRecord): void {
    this.corpus.push({ ...record, vector: [], norm: 0 });
    this.dirty = true;
  }

  addAll(records: VectorRecord[]): void {
    records.forEach(r => this.add(r));
  }

  clear(): void {
    this.corpus = [];
    this.vocab  = new Map();
    this.idf    = [];
    this.dirty  = false;
  }

  get size(): number { return this.corpus.length; }

  // ── Index building ──────────────────────────────────────────────────────────

  buildIndex(): void {
    if (!this.dirty) return;

    const N = this.corpus.length;
    if (N === 0) return;

    // Build vocabulary
    this.vocab = new Map();
    let col = 0;
    const tokenLists: string[][] = this.corpus.map(r => tokenise(r.text));

    for (const tokens of tokenLists) {
      for (const t of tokens) {
        if (!this.vocab.has(t)) this.vocab.set(t, col++);
      }
    }

    const V = this.vocab.size;

    // Document frequency per term
    const df = new Float64Array(V);
    for (const tokens of tokenLists) {
      const seen = new Set(tokens);
      for (const t of seen) {
        const i = this.vocab.get(t);
        if (i !== undefined) df[i]++;
      }
    }

    // IDF = log((N + 1) / (df + 1)) + 1   (smoothed)
    this.idf = Array.from(df).map(d => Math.log((N + 1) / (d + 1)) + 1);

    // Build TF-IDF vectors
    for (let ri = 0; ri < N; ri++) {
      const tf = termFrequency(tokenLists[ri]);
      const vec = new Float64Array(V);
      for (const [term, tfVal] of tf) {
        const i = this.vocab.get(term);
        if (i !== undefined) vec[i] = tfVal * this.idf[i];
      }
      const norm = Math.sqrt(vec.reduce((s, x) => s + x * x, 0));
      this.corpus[ri].vector = Array.from(vec);
      this.corpus[ri].norm   = norm || 1;
    }

    this.dirty = false;
  }

  // ── Query ───────────────────────────────────────────────────────────────────

  search(query: string, topK = 5, filterType?: RecordType): SearchResult[] {
    if (this.dirty) this.buildIndex();
    if (this.corpus.length === 0) return [];

    const V    = this.vocab.size;
    const qtf  = termFrequency(tokenise(query));
    const qvec = new Float64Array(V);

    for (const [term, tfVal] of qtf) {
      const i = this.vocab.get(term);
      if (i !== undefined) qvec[i] = tfVal * this.idf[i];
    }

    const qnorm = Math.sqrt(qvec.reduce((s, x) => s + x * x, 0)) || 1;

    const pool = filterType ? this.corpus.filter(r => r.type === filterType) : this.corpus;

    const scored = pool.map(r => {
      let dot = 0;
      for (let i = 0; i < V; i++) dot += qvec[i] * (r.vector[i] ?? 0);
      return { record: r as VectorRecord, score: dot / (qnorm * r.norm) };
    });

    scored.sort((a, b) => b.score - a.score);
    return scored.slice(0, topK).filter(s => s.score > 0);
  }

  // ── All records by type ─────────────────────────────────────────────────────

  getByType(type: RecordType): VectorRecord[] {
    return this.corpus.filter(r => r.type === type);
  }

  all(): VectorRecord[] {
    return this.corpus;
  }
}

// Singleton shared across the app
export const vectorDb = new VectorDB();
