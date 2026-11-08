import { useEffect, useRef, useState } from "react";
import type * as Leaflet from "leaflet";
import { formatWhen, type PlaceGroup } from "@/lib/events";

const UBC_CENTER: [number, number] = [49.2645, -123.251];
const UBC_BOUNDS: [[number, number], [number, number]] = [
  [49.245, -123.272],
  [49.282, -123.228],
];

/**
 * UBC map with one pin per building. Leaflet touches `window`, so it is loaded in the browser
 * only; during SSR this renders an empty frame. Popup text is set with textContent (venue and
 * titles come from scraped posts), never innerHTML.
 */
export function CampusMap({
  pins,
  selected,
  onSelect,
  onOpenEvent,
}: {
  pins: PlaceGroup[];
  selected: string | null;
  onSelect: (placeId: string | null) => void;
  onOpenEvent: (eventId: string) => void;
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<Leaflet.Map | null>(null);
  const layer = useRef<Leaflet.LayerGroup | null>(null);
  const markers = useRef(new Map<string, Leaflet.Marker>());
  const L = useRef<typeof Leaflet | null>(null);
  const [ready, setReady] = useState(false);
  const handlers = useRef({ onSelect, onOpenEvent });
  handlers.current = { onSelect, onOpenEvent };

  // Create the map once.
  useEffect(() => {
    let cancelled = false;
    void Promise.all([import("leaflet"), import("leaflet/dist/leaflet.css")]).then(([mod]) => {
      if (cancelled || !el.current || map.current) return;
      const lf =
        (mod as unknown as { default?: typeof Leaflet }).default ?? (mod as typeof Leaflet);
      L.current = lf;
      const m = lf.map(el.current, {
        center: UBC_CENTER,
        zoom: 15,
        minZoom: 14,
        maxZoom: 19,
        maxBounds: UBC_BOUNDS,
        maxBoundsViscosity: 0.8,
        scrollWheelZoom: false, // don't hijack page scroll; pinch and +/- still zoom
      });
      lf.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }).addTo(m);
      m.on("click", () => handlers.current.onSelect(null));
      layer.current = lf.layerGroup().addTo(m);
      map.current = m;
      setReady(true);
    });
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
    };
  }, []);

  // Redraw pins when the day changes.
  useEffect(() => {
    const lf = L.current;
    const m = map.current;
    if (!ready || !lf || !m || !layer.current) return;
    layer.current.clearLayers();
    markers.current.clear();
    for (const g of pins) {
      const icon = lf.divIcon({
        className: "map-pin-wrap",
        html: `<span class="map-pin">${g.events.length}</span>`,
        iconSize: [34, 34],
        iconAnchor: [17, 17],
        popupAnchor: [0, -18],
      });
      const marker = lf
        .marker([g.place.lat, g.place.lng], {
          icon,
          title: g.place.name,
          alt: `${g.place.name}: ${g.events.length} event${g.events.length > 1 ? "s" : ""}`,
          keyboard: true,
        })
        .bindPopup(() => popup(g, (id) => handlers.current.onOpenEvent(id)), { minWidth: 220 })
        .on("click", () => handlers.current.onSelect(g.place.id))
        .on("popupclose", () => handlers.current.onSelect(null))
        .addTo(layer.current);
      markers.current.set(g.place.id, marker);
    }
    if (pins.length) {
      const bounds = lf.latLngBounds(
        pins.map((g) => [g.place.lat, g.place.lng] as [number, number]),
      );
      m.fitBounds(bounds.pad(0.3), { maxZoom: 16, animate: false }); // keep campus context
    } else {
      m.setView(UBC_CENTER, 15, { animate: false });
    }
  }, [pins, ready]);

  // Follow selection from the list beside the map.
  useEffect(() => {
    if (!ready || !selected) return;
    const marker = markers.current.get(selected);
    if (marker && !marker.isPopupOpen()) {
      map.current?.panTo(marker.getLatLng());
      marker.openPopup();
    }
  }, [selected, ready]);

  return (
    <div
      ref={el}
      className="campus-map h-[55vh] min-h-[320px] w-full overflow-hidden rounded-2xl border border-border bg-muted"
      role="region"
      aria-label="Map of UBC Vancouver campus with today's events"
    />
  );
}

function popup(g: PlaceGroup, open: (id: string) => void): HTMLElement {
  const root = document.createElement("div");
  root.className = "map-popup";
  const h = document.createElement("p");
  h.className = "map-popup-title";
  h.textContent = g.place.name;
  root.append(h);
  const ul = document.createElement("ul");
  for (const e of g.events) {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = `/events/${encodeURIComponent(e.id)}`;
    a.textContent = e.title;
    a.addEventListener("click", (ev) => {
      ev.preventDefault();
      open(e.id);
    });
    const meta = document.createElement("span");
    meta.textContent = `${formatWhen(e).split(" · ")[1] ?? "Time TBD"} · ${e.venue ?? ""}`;
    li.append(a, meta);
    ul.append(li);
  }
  root.append(ul);
  return root;
}
