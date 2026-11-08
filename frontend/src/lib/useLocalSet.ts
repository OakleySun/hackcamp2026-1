import { useEffect, useState } from "react";

export function useLocalSet(key: string) {
  const [set, setSet] = useState<Set<string>>(new Set());
  useEffect(() => {
    try {
      setSet(new Set(JSON.parse(localStorage.getItem(key) ?? "[]")));
    } catch {
      /* ignore */
    }
  }, [key]);
  const toggle = (id: string) =>
    setSet((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      localStorage.setItem(key, JSON.stringify([...n]));
      return n;
    });
  return [set, toggle] as const;
}
