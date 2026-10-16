// In-memory stand-in for the read slice of the document-reader interface (lib/replay/snapshot.ts ReadDb), for tests.
import type { Coll, Doc, ReadDb } from "./snapshot";

const matches = (d: Doc, filter: Doc) =>
  Object.entries(filter).every(([k, v]) => {
    if (v && typeof v === "object" && "$in" in (v as Doc)) return ((v as { $in: unknown[] }).$in).includes(d[k]);
    return d[k] === v;
  });

function project(d: Doc, projection?: Doc): Doc {
  if (!projection) return { ...d };
  const excluded = Object.entries(projection).filter(([, v]) => v === 0).map(([k]) => k);
  const included = Object.entries(projection).filter(([, v]) => v === 1).map(([k]) => k);
  if (included.length) return Object.fromEntries(Object.entries(d).filter(([k]) => included.includes(k) || (k === "_id" && !excluded.includes("_id"))));
  return Object.fromEntries(Object.entries(d).filter(([k]) => !excluded.includes(k)));
}

export function fakeDb(data: Record<string, Doc[]>): ReadDb & { reads: string[] } {
  const reads: string[] = [];
  return {
    reads,
    collection(name: string): Coll {
      const docs = data[name] ?? [];
      return {
        find(filter, options = {}) {
          reads.push(name);
          let out = docs.filter((d) => matches(d, filter));
          if (options.sort) {
            const [[key, dir]] = Object.entries(options.sort) as [[string, 1 | -1]];
            out = [...out].sort((a, b) => ((a[key] as number) - (b[key] as number)) * dir);
          }
          if (options.limit) out = out.slice(0, options.limit);
          return { toArray: async () => out.map((d) => project(d, options.projection)) };
        },
        async findOne(filter, options = {}) {
          reads.push(name);
          const d = docs.find((x) => matches(x, filter));
          return d ? project(d, options.projection) : null;
        },
      };
    },
  };
}
