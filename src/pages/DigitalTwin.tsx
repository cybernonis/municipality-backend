import React, { useEffect, useState, useCallback, useRef } from "react";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
  Tooltip,
  Polygon,
  useMap,
} from "react-leaflet";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip as RechartTooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import axios from "axios";
import "leaflet/dist/leaflet.css";

const API = import.meta.env.VITE_API_URL || "https://municipality-backend-production.up.railway.app";
const HERAKLION: [number, number] = [35.3387, 25.1442];

// ─── Types ───────────────────────────────────────────────
interface WeatherData {
  temperature: number;
  feels_like: number;
  humidity: number;
  description: string;
  wind_speed: number;
  wind_kmh: number;
  rain_probability: number;
  rain_mm: number;
  alerts: { type: string; message: string }[];
  icon: string;
  forecast_24h: { time: string; temp: number; rain_probability: number; description: string }[];
  source: string;
}

interface TrafficData {
  congestion_level: string;
  congestion_percentage: number;
  incidents: { type: string; location: string; severity: string; lat: number; lng: number }[];
  affected_roads: string[];
  source: string;
}

interface HazardsData {
  fires: { lat: number; lng: number; confidence: number; brightness: number; detected_at: string; distance_km: number }[];
  nearby_fires: unknown[];
  auto_crisis: boolean;
  last_updated: string;
  source: string;
}

interface AirQualityData {
  aqi: number;
  pm25: number;
  pm10: number;
  no2: number;
  o3: number;
  status: string;
  color: string;
  source: string;
}

interface EarthquakeData {
  earthquakes: { magnitude: number; depth_km: number; lat: number; lng: number; time: string; felt: boolean; place: string; distance_km: number }[];
  significant: unknown[];
  total: number;
  last_updated: string;
  source: string;
}

interface Report { id: string; lat: number; lng: number; category: string; severity: string; status: string }
interface IoTDevice { id: string; lat: number; lng: number; device_type: string; name: string; status: string; battery: number }
interface CrisisEvent { id: string; lat: number; lng: number; crisis_type: string; severity: string }

// ─── Helpers ──────────────────────────────────────────────
const congestionColor = (level: string) =>
  ({ low: "#22c55e", moderate: "#f59e0b", high: "#ef4444", unknown: "#6b7280" }[level] ?? "#6b7280");

const severityColor = (s: string) =>
  ({ critical: "#dc2626", high: "#ea580c", medium: "#ca8a04", low: "#16a34a" }[s] ?? "#6b7280");

const categoryColor = (c: string) =>
  ({ road_damage: "#f97316", garbage: "#84cc16", graffiti: "#a855f7", flooding: "#3b82f6", other: "#6b7280" }[c] ?? "#6b7280");

function WeatherIcon({ icon, size = 40 }: { icon: string; size?: number }) {
  return (
    <img
      src={`https://openweathermap.org/img/wn/${icon}@2x.png`}
      alt="weather"
      style={{ width: size, height: size }}
    />
  );
}

// ─── Leaflet heatmap layer helper ─────────────────────────
function HeatmapLayer({ points }: { points: { lat: number; lng: number; intensity: number }[] }) {
  const map = useMap();
  useEffect(() => {
    if (!points.length) return;
    // @ts-ignore — leaflet.heat is loaded via CDN/import
    const heat = (window as any).L?.heatLayer(
      points.map((p) => [p.lat, p.lng, p.intensity]),
      { radius: 25, blur: 15, maxZoom: 17 }
    );
    if (heat) {
      heat.addTo(map);
      return () => map.removeLayer(heat);
    }
  }, [map, points]);
  return null;
}

// ─── Main Component ────────────────────────────────────────
export default function DigitalTwin() {
  // Map layers state
  const [layers, setLayers] = useState({
    reports: true,
    iot: true,
    crises: true,
    heatmap: false,
    traffic: true,
    fires: true,
    earthquakes: true,
  });

  // City data
  const [reports, setReports] = useState<Report[]>([]);
  const [iotDevices, setIotDevices] = useState<IoTDevice[]>([]);
  const [crises, setCrises] = useState<CrisisEvent[]>([]);
  const [heatmapPoints, setHeatmapPoints] = useState<{ lat: number; lng: number; intensity: number }[]>([]);

  // External data
  const [weather, setWeather] = useState<WeatherData | null>(null);
  const [traffic, setTraffic] = useState<TrafficData | null>(null);
  const [hazards, setHazards] = useState<HazardsData | null>(null);
  const [airQuality, setAirQuality] = useState<AirQualityData | null>(null);
  const [earthquakes, setEarthquakes] = useState<EarthquakeData | null>(null);

  // UI state
  const [smartAlerts, setSmartAlerts] = useState<{ type: string; message: string; source: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"layers" | "live">("live");
  const wsRef = useRef<WebSocket | null>(null);

  // ── Fetch city data ──────────────────────────────────────
  const fetchCityData = useCallback(async () => {
    try {
      const [layersRes, heatRes] = await Promise.all([
        axios.get(`${API}/digital-twin/layers`),
        axios.get(`${API}/digital-twin/heatmap`),
      ]);
      setReports(layersRes.data.reports || []);
      setIotDevices(layersRes.data.iot_devices || []);
      setCrises(layersRes.data.crises || []);
      setHeatmapPoints(heatRes.data.points || []);
    } catch (err) {
      console.error("City data fetch error:", err);
    }
  }, []);

  // ── Fetch external data ──────────────────────────────────
  const fetchExternalData = useCallback(async () => {
    try {
      const [wRes, tRes, hRes, aqRes, eqRes] = await Promise.all([
        axios.get(`${API}/external/weather`),
        axios.get(`${API}/external/traffic`),
        axios.get(`${API}/external/hazards`),
        axios.get(`${API}/external/air-quality`),
        axios.get(`${API}/external/earthquakes`),
      ]);

      setWeather(wRes.data);
      setTraffic(tRes.data);
      setHazards(hRes.data);
      setAirQuality(aqRes.data);
      setEarthquakes(eqRes.data);

      // Build smart alerts
      const alerts: { type: string; message: string; source: string }[] = [];
      const w: WeatherData = wRes.data;
      const h: HazardsData = hRes.data;
      const eq: EarthquakeData = eqRes.data;
      const aq: AirQualityData = aqRes.data;

      w.alerts.forEach((a) => alerts.push({ ...a, source: "weather" }));
      if (h.auto_crisis)
        alerts.push({ type: "fire", message: `Ενεργή πυρκαγιά εντός 50km — ${h.nearby_fires.length} εστίες`, source: "hazards" });
      eq.significant.forEach((s: any) =>
        alerts.push({ type: "earthquake", message: `Σεισμός ${s.magnitude}R — ${s.place}`, source: "earthquakes" })
      );
      if (aq.aqi > 100)
        alerts.push({ type: "air", message: `Κακή ποιότητα αέρα — AQI ${aq.aqi}`, source: "air_quality" });

      setSmartAlerts(alerts);
    } catch (err) {
      console.error("External data fetch error:", err);
    }
  }, []);

  // ── Initial load ─────────────────────────────────────────
  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await Promise.all([fetchCityData(), fetchExternalData()]);
      setLoading(false);
    };
    init();

    // Refresh intervals
    const cityInterval = setInterval(fetchCityData, 30_000);
    const weatherInterval = setInterval(() => axios.get(`${API}/external/weather`).then((r) => setWeather(r.data)), 600_000);
    const trafficInterval = setInterval(() => axios.get(`${API}/external/traffic`).then((r) => setTraffic(r.data)), 120_000);
    const externalInterval = setInterval(fetchExternalData, 300_000);

    return () => {
      clearInterval(cityInterval);
      clearInterval(weatherInterval);
      clearInterval(trafficInterval);
      clearInterval(externalInterval);
    };
  }, [fetchCityData, fetchExternalData]);

  // ── WebSocket ────────────────────────────────────────────
  useEffect(() => {
    const wsUrl = API.replace("https://", "wss://").replace("http://", "ws://");
    const ws = new WebSocket(`${wsUrl}/ws`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "new_report" || msg.type === "report_updated") {
        fetchCityData();
      }
      if (msg.type === "external_alert" && msg.alerts?.length) {
        setSmartAlerts((prev) => {
          const incoming = msg.alerts as { type: string; message: string; source: string }[];
          const merged = [...prev];
          incoming.forEach((a) => {
            if (!merged.find((m) => m.message === a.message)) merged.push(a);
          });
          return merged.slice(0, 10);
        });
      }
    };

    return () => ws.close();
  }, [fetchCityData]);

  const toggleLayer = (key: keyof typeof layers) =>
    setLayers((prev) => ({ ...prev, [key]: !prev[key] }));

  const alertIcon = (type: string) =>
    ({ weather: "🌧", rain: "🌧", flood: "🌊", wind: "💨", heat: "🌡", fire: "🔥", earthquake: "🫨", air: "💨" }[type] ?? "⚠️");

  const incidentTypeLabel = (type: string) =>
    ({ accident: "Ατύχημα", jam: "Κυκλοφοριακή συμφόρηση", road_works: "Εργασίες", road_closed: "Κλειστός δρόμος", flooding: "Πλημμύρα" }[type] ?? type);

  // ── Render ───────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-900 text-white">
        <div className="text-center">
          <div className="animate-spin text-5xl mb-4">🌐</div>
          <p className="text-xl">Φόρτωση Digital Twin Ηρακλείου...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-gray-900 text-white overflow-hidden">
      {/* ── Sidebar ── */}
      <div className="w-80 flex flex-col bg-gray-800 border-r border-gray-700 overflow-y-auto z-10">
        {/* Header */}
        <div className="p-4 border-b border-gray-700">
          <h1 className="text-lg font-bold text-blue-400">Digital Twin Ηρακλείου</h1>
          <p className="text-xs text-gray-400 mt-1">Ζωντανή Παρακολούθηση Πόλης</p>

          {/* Tabs */}
          <div className="flex mt-3 bg-gray-700 rounded-lg p-1">
            {(["live", "layers"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`flex-1 text-xs py-1 rounded-md transition-colors ${
                  activeTab === tab ? "bg-blue-600 text-white" : "text-gray-400 hover:text-white"
                }`}
              >
                {tab === "live" ? "Live Data" : "Επίπεδα"}
              </button>
            ))}
          </div>
        </div>

        {/* Smart Alerts Banner */}
        {smartAlerts.length > 0 && (
          <div className="p-3 bg-red-900/40 border-b border-red-700">
            <p className="text-xs font-bold text-red-400 mb-2">⚠ ΕΝΕΡΓΕΣ ΕΙΔΟΠΟΙΗΣΕΙΣ</p>
            <div className="space-y-1 max-h-32 overflow-y-auto">
              {smartAlerts.map((a, i) => (
                <div key={i} className="text-xs bg-red-900/50 rounded p-2 flex items-start gap-2">
                  <span>{alertIcon(a.type)}</span>
                  <span className="text-red-200">{a.message}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── LIVE DATA TAB ── */}
        {activeTab === "live" && (
          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            {/* Weather Widget */}
            {weather && (
              <div className="bg-gradient-to-br from-blue-900/60 to-blue-800/40 rounded-xl p-3 border border-blue-700/50">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-blue-300">ΚΑΙΡΟΣ ΗΡΑΚΛΕΙΟΥ</span>
                  {weather.source === "fallback" && (
                    <span className="text-xs text-yellow-500">Demo</span>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <WeatherIcon icon={weather.icon} size={48} />
                  <div>
                    <div className="text-3xl font-bold">{Math.round(weather.temperature)}°C</div>
                    <div className="text-xs text-gray-300 capitalize">{weather.description}</div>
                    <div className="text-xs text-gray-400">Αίσθηση {Math.round(weather.feels_like)}°C</div>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2 mt-3 text-center">
                  <div className="bg-blue-900/40 rounded p-2">
                    <div className="text-xs text-gray-400">Υγρασία</div>
                    <div className="text-sm font-bold">{weather.humidity}%</div>
                  </div>
                  <div className="bg-blue-900/40 rounded p-2">
                    <div className="text-xs text-gray-400">Άνεμος</div>
                    <div className="text-sm font-bold">{weather.wind_kmh} km/h</div>
                  </div>
                  <div className="bg-blue-900/40 rounded p-2">
                    <div className="text-xs text-gray-400">Βροχή</div>
                    <div className="text-sm font-bold">{Math.round(weather.rain_probability * 100)}%</div>
                  </div>
                </div>

                {/* 24h Forecast */}
                {weather.forecast_24h.length > 0 && (
                  <div className="mt-3">
                    <div className="text-xs text-gray-400 mb-1">Πρόγνωση 24ω</div>
                    <ResponsiveContainer width="100%" height={60}>
                      <BarChart data={weather.forecast_24h.slice(0, 8)}>
                        <XAxis
                          dataKey="time"
                          tick={{ fontSize: 9, fill: "#9ca3af" }}
                          tickFormatter={(v) => v.split(" ")[1]?.slice(0, 5) ?? ""}
                          interval={1}
                        />
                        <YAxis hide domain={[0, 1]} />
                        <RechartTooltip
                          formatter={(v: number) => [`${Math.round(v * 100)}%`, "Βροχή"]}
                          labelFormatter={(l) => l.split(" ")[1] ?? ""}
                          contentStyle={{ background: "#1f2937", border: "none", fontSize: 11 }}
                        />
                        <Bar dataKey="rain_probability" radius={[3, 3, 0, 0]}>
                          {weather.forecast_24h.slice(0, 8).map((_, i) => (
                            <Cell
                              key={i}
                              fill={weather.forecast_24h[i].rain_probability > 0.5 ? "#3b82f6" : "#1d4ed8"}
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>
            )}

            {/* Air Quality */}
            {airQuality && (
              <div className="bg-gray-700/50 rounded-xl p-3 border border-gray-600">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-green-300">ΠΟΙΟΤΗΤΑ ΑΕΡΑ</span>
                  <span
                    className="text-xs px-2 py-0.5 rounded-full font-bold"
                    style={{ background: airQuality.color + "33", color: airQuality.color }}
                  >
                    {airQuality.status}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <div
                    className="w-14 h-14 rounded-full flex items-center justify-center text-xl font-bold border-4"
                    style={{ borderColor: airQuality.color, color: airQuality.color }}
                  >
                    {airQuality.aqi}
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                    <span className="text-gray-400">PM2.5</span><span>{airQuality.pm25} μg/m³</span>
                    <span className="text-gray-400">PM10</span><span>{airQuality.pm10} μg/m³</span>
                    <span className="text-gray-400">NO₂</span><span>{airQuality.no2} μg/m³</span>
                    <span className="text-gray-400">O₃</span><span>{airQuality.o3} μg/m³</span>
                  </div>
                </div>
              </div>
            )}

            {/* Traffic */}
            {traffic && (
              <div className="bg-gray-700/50 rounded-xl p-3 border border-gray-600">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-yellow-300">ΚΥΚΛΟΦΟΡΙΑ</span>
                  <span
                    className="text-xs px-2 py-0.5 rounded-full font-bold"
                    style={{
                      background: congestionColor(traffic.congestion_level) + "33",
                      color: congestionColor(traffic.congestion_level),
                    }}
                  >
                    {({ low: "Ελεύθερη", moderate: "Μέτρια", high: "Πυκνή", unknown: "Άγνωστη" }[traffic.congestion_level] ?? traffic.congestion_level)}
                  </span>
                </div>

                {/* Congestion bar */}
                <div className="w-full bg-gray-600 rounded-full h-2 mb-3">
                  <div
                    className="h-2 rounded-full transition-all"
                    style={{
                      width: `${traffic.congestion_percentage}%`,
                      background: congestionColor(traffic.congestion_level),
                    }}
                  />
                </div>

                {traffic.incidents.length > 0 && (
                  <div className="space-y-1 max-h-28 overflow-y-auto">
                    {traffic.incidents.map((inc, i) => (
                      <div key={i} className="text-xs bg-gray-600/50 rounded p-1.5 flex gap-2">
                        <span style={{ color: severityColor(inc.severity) }}>●</span>
                        <div>
                          <div className="font-medium">{incidentTypeLabel(inc.type)}</div>
                          <div className="text-gray-400">{inc.location}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {traffic.source === "fallback" && (
                  <p className="text-xs text-yellow-600 mt-1">Demo δεδομένα</p>
                )}
              </div>
            )}

            {/* Earthquakes */}
            {earthquakes && (
              <div className="bg-gray-700/50 rounded-xl p-3 border border-gray-600">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-orange-300">ΣΕΙΣΜΙΚΗ ΔΡΑΣΤΗΡΙΟΤΗΤΑ</span>
                  <span className="text-xs text-gray-400">{earthquakes.total} / 7 ημέρες</span>
                </div>
                {earthquakes.earthquakes.slice(0, 5).map((eq, i) => (
                  <div key={i} className="flex items-center gap-2 py-1 border-b border-gray-600/50 last:border-0">
                    <div
                      className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold border-2 flex-shrink-0"
                      style={{
                        borderColor: eq.magnitude >= 4 ? "#dc2626" : eq.magnitude >= 3 ? "#f59e0b" : "#22c55e",
                        color: eq.magnitude >= 4 ? "#dc2626" : eq.magnitude >= 3 ? "#f59e0b" : "#22c55e",
                      }}
                    >
                      {eq.magnitude.toFixed(1)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs truncate">{eq.place}</div>
                      <div className="text-xs text-gray-400">{eq.distance_km} km · {eq.depth_km} km βάθος</div>
                    </div>
                    {eq.felt && <span className="text-xs text-yellow-400">Felt</span>}
                  </div>
                ))}
                {earthquakes.earthquakes.length === 0 && (
                  <p className="text-xs text-gray-400 text-center py-2">Δεν καταγράφηκαν σεισμοί</p>
                )}
              </div>
            )}

            {/* Fire Hazards */}
            {hazards && (
              <div
                className="rounded-xl p-3 border"
                style={{
                  background: hazards.auto_crisis ? "rgba(220,38,38,0.15)" : "rgba(55,65,81,0.5)",
                  borderColor: hazards.auto_crisis ? "#dc2626" : "#4b5563",
                }}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-red-300">ΠΥΡΚΑΓΙΕΣ / ΚΙΝΔΥΝΟΙ</span>
                  {hazards.auto_crisis && (
                    <span className="text-xs bg-red-600 px-2 py-0.5 rounded-full animate-pulse">ΚΙΝΔΥΝΟΣ</span>
                  )}
                </div>
                <div className="text-xs text-gray-400 mb-1">
                  Εστίες στην Κρήτη: <span className="text-white font-bold">{hazards.fires.length}</span>
                  {" · "}
                  Εντός 50km: <span className={hazards.nearby_fires.length > 0 ? "text-red-400 font-bold" : "text-white font-bold"}>
                    {hazards.nearby_fires.length}
                  </span>
                </div>
                {hazards.fires.slice(0, 3).map((f, i) => (
                  <div key={i} className="text-xs bg-red-900/30 rounded p-1.5 mb-1">
                    🔥 {f.distance_km} km — Εμπιστοσύνη {f.confidence}%
                  </div>
                ))}
                <div className="text-xs text-gray-500 mt-1">
                  Πηγή: NASA FIRMS · {new Date(hazards.last_updated).toLocaleTimeString("el-GR")}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── LAYERS TAB ── */}
        {activeTab === "layers" && (
          <div className="p-3 space-y-2">
            <p className="text-xs text-gray-400 font-bold mb-3">ΕΠΙΠΕΔΑ ΧΑΡΤΗ</p>
            {(
              [
                { key: "reports", label: "Αναφορές Πολιτών", color: "#f97316", emoji: "📍" },
                { key: "iot", label: "IoT Συσκευές", color: "#22c55e", emoji: "📡" },
                { key: "crises", label: "Κρίσεις", color: "#dc2626", emoji: "🚨" },
                { key: "heatmap", label: "Heatmap", color: "#f59e0b", emoji: "🌡" },
                { key: "traffic", label: "Περιστατικά Κυκλοφορίας", color: "#facc15", emoji: "🚗" },
                { key: "fires", label: "Εστίες Πυρκαγιάς", color: "#ef4444", emoji: "🔥" },
                { key: "earthquakes", label: "Σεισμοί", color: "#f97316", emoji: "🫨" },
              ] as { key: keyof typeof layers; label: string; color: string; emoji: string }[]
            ).map(({ key, label, color, emoji }) => (
              <button
                key={key}
                onClick={() => toggleLayer(key)}
                className={`w-full flex items-center gap-3 p-2.5 rounded-lg border transition-all text-left ${
                  layers[key]
                    ? "border-opacity-60 bg-opacity-20"
                    : "border-gray-700 bg-gray-700/30 opacity-50"
                }`}
                style={layers[key] ? { borderColor: color, background: color + "20" } : undefined}
              >
                <span>{emoji}</span>
                <span className="text-sm">{label}</span>
                <div
                  className={`ml-auto w-8 h-4 rounded-full transition-colors ${layers[key] ? "bg-blue-600" : "bg-gray-600"}`}
                >
                  <div
                    className={`w-4 h-4 bg-white rounded-full shadow transition-transform ${layers[key] ? "translate-x-4" : "translate-x-0"}`}
                  />
                </div>
              </button>
            ))}

            {/* Summary stats */}
            <div className="mt-4 pt-4 border-t border-gray-700 grid grid-cols-2 gap-2 text-center">
              <div className="bg-gray-700/50 rounded p-2">
                <div className="text-lg font-bold text-blue-400">{reports.length}</div>
                <div className="text-xs text-gray-400">Αναφορές</div>
              </div>
              <div className="bg-gray-700/50 rounded p-2">
                <div className="text-lg font-bold text-green-400">{iotDevices.length}</div>
                <div className="text-xs text-gray-400">IoT Συσκευές</div>
              </div>
              <div className="bg-gray-700/50 rounded p-2">
                <div className="text-lg font-bold text-red-400">{crises.length}</div>
                <div className="text-xs text-gray-400">Κρίσεις</div>
              </div>
              <div className="bg-gray-700/50 rounded p-2">
                <div className="text-lg font-bold text-yellow-400">{hazards?.fires.length ?? 0}</div>
                <div className="text-xs text-gray-400">Εστίες φωτιάς</div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Map ── */}
      <div className="flex-1 relative">
        <MapContainer
          center={HERAKLION}
          zoom={13}
          style={{ height: "100%", width: "100%", background: "#1a1a2e" }}
          className="z-0"
        >
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            attribution='&copy; <a href="https://carto.com/">CARTO</a>'
          />

          {/* Heatmap */}
          {layers.heatmap && <HeatmapLayer points={heatmapPoints} />}

          {/* Reports */}
          {layers.reports &&
            reports.map((r) => (
              <CircleMarker
                key={r.id}
                center={[r.lat, r.lng]}
                radius={r.severity === "high" ? 10 : r.severity === "medium" ? 7 : 5}
                pathOptions={{ color: categoryColor(r.category), fillColor: categoryColor(r.category), fillOpacity: 0.8, weight: 2 }}
              >
                <Tooltip permanent={false}>{r.category} · {r.severity}</Tooltip>
                <Popup>
                  <div className="text-sm">
                    <b>Αναφορά</b><br />
                    Κατηγορία: {r.category}<br />
                    Σοβαρότητα: {r.severity}<br />
                    Κατάσταση: {r.status}
                  </div>
                </Popup>
              </CircleMarker>
            ))}

          {/* IoT Devices */}
          {layers.iot &&
            iotDevices.map((d) => (
              <CircleMarker
                key={d.id}
                center={[d.lat, d.lng]}
                radius={6}
                pathOptions={{
                  color: d.status === "active" ? "#22c55e" : "#ef4444",
                  fillColor: d.status === "active" ? "#22c55e" : "#ef4444",
                  fillOpacity: 0.9,
                  weight: 2,
                }}
              >
                <Tooltip>{d.name}</Tooltip>
                <Popup>
                  <div className="text-sm">
                    <b>{d.name}</b><br />
                    Τύπος: {d.device_type}<br />
                    Κατάσταση: {d.status}<br />
                    Μπαταρία: {d.battery}%
                  </div>
                </Popup>
              </CircleMarker>
            ))}

          {/* Crisis Events */}
          {layers.crises &&
            crises.map((c) => (
              <CircleMarker
                key={c.id}
                center={[c.lat, c.lng]}
                radius={14}
                pathOptions={{ color: "#dc2626", fillColor: "#dc2626", fillOpacity: 0.3, weight: 3, dashArray: "6 4" }}
              >
                <Tooltip permanent className="crisis-tooltip">{c.crisis_type}</Tooltip>
                <Popup>
                  <div className="text-sm">
                    <b>🚨 Κρίση: {c.crisis_type}</b><br />
                    Σοβαρότητα: {c.severity}
                  </div>
                </Popup>
              </CircleMarker>
            ))}

          {/* Traffic Incidents */}
          {layers.traffic &&
            traffic?.incidents.map((inc, i) => (
              <CircleMarker
                key={i}
                center={[inc.lat, inc.lng]}
                radius={8}
                pathOptions={{
                  color: severityColor(inc.severity),
                  fillColor: severityColor(inc.severity),
                  fillOpacity: 0.85,
                  weight: 2,
                }}
              >
                <Tooltip>{incidentTypeLabel(inc.type)}</Tooltip>
                <Popup>
                  <div className="text-sm">
                    <b>🚗 {incidentTypeLabel(inc.type)}</b><br />
                    Τοποθεσία: {inc.location}<br />
                    Σοβαρότητα: {inc.severity}
                  </div>
                </Popup>
              </CircleMarker>
            ))}

          {/* Fire Locations */}
          {layers.fires &&
            hazards?.fires.map((fire, i) => (
              <CircleMarker
                key={i}
                center={[fire.lat, fire.lng]}
                radius={6 + Math.min(fire.confidence / 20, 6)}
                pathOptions={{ color: "#dc2626", fillColor: "#f97316", fillOpacity: 0.9, weight: 2 }}
              >
                <Tooltip>🔥 Εστία φωτιάς · {fire.distance_km} km</Tooltip>
                <Popup>
                  <div className="text-sm">
                    <b>🔥 Εστία Πυρκαγιάς</b><br />
                    Απόσταση: {fire.distance_km} km<br />
                    Εμπιστοσύνη: {fire.confidence}%<br />
                    Φωτεινότητα: {fire.brightness}<br />
                    Ανιχνεύθηκε: {new Date(fire.detected_at).toLocaleString("el-GR")}
                  </div>
                </Popup>
              </CircleMarker>
            ))}

          {/* Earthquake Epicenters */}
          {layers.earthquakes &&
            earthquakes?.earthquakes.map((eq, i) => (
              <CircleMarker
                key={i}
                center={[eq.lat, eq.lng]}
                radius={Math.max(4, eq.magnitude * 4)}
                pathOptions={{
                  color: eq.magnitude >= 4 ? "#dc2626" : eq.magnitude >= 3 ? "#f59e0b" : "#22c55e",
                  fillColor: eq.magnitude >= 4 ? "#dc2626" : eq.magnitude >= 3 ? "#f59e0b" : "#22c55e",
                  fillOpacity: 0.4,
                  weight: 2,
                }}
              >
                <Tooltip>M{eq.magnitude.toFixed(1)} · {eq.place}</Tooltip>
                <Popup>
                  <div className="text-sm">
                    <b>🫨 Σεισμός M{eq.magnitude.toFixed(1)}</b><br />
                    {eq.place}<br />
                    Βάθος: {eq.depth_km} km<br />
                    Απόσταση: {eq.distance_km} km<br />
                    {new Date(eq.time).toLocaleString("el-GR")}
                    {eq.felt && <><br /><span className="text-yellow-600">Felt</span></>}
                  </div>
                </Popup>
              </CircleMarker>
            ))}
        </MapContainer>

        {/* Map legend overlay */}
        <div className="absolute bottom-4 right-4 bg-gray-800/90 backdrop-blur-sm rounded-lg p-3 z-[1000] text-xs space-y-1">
          <div className="font-bold text-gray-300 mb-2">Υπόμνημα</div>
          {[
            { color: "#f97316", label: "Αναφορά" },
            { color: "#22c55e", label: "IoT Ενεργή" },
            { color: "#ef4444", label: "IoT Βλάβη / Κρίση" },
            { color: "#facc15", label: "Κυκλοφορία" },
            { color: "#f97316", label: "Φωτιά" },
            { color: "#f59e0b", label: "Σεισμός M3+" },
            { color: "#dc2626", label: "Σεισμός M4+" },
          ].map(({ color, label }) => (
            <div key={label} className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full" style={{ background: color }} />
              <span className="text-gray-300">{label}</span>
            </div>
          ))}
        </div>

        {/* Top status bar */}
        <div className="absolute top-4 left-1/2 -translate-x-1/2 flex gap-2 z-[1000]">
          {weather && (
            <div className="bg-gray-800/90 backdrop-blur-sm rounded-full px-3 py-1.5 text-xs flex items-center gap-2">
              <WeatherIcon icon={weather.icon} size={20} />
              <span className="font-bold">{Math.round(weather.temperature)}°C</span>
              <span className="text-gray-400">{weather.description}</span>
            </div>
          )}
          {airQuality && (
            <div
              className="backdrop-blur-sm rounded-full px-3 py-1.5 text-xs flex items-center gap-2"
              style={{ background: airQuality.color + "22", border: `1px solid ${airQuality.color}66` }}
            >
              <span style={{ color: airQuality.color }}>AQI {airQuality.aqi}</span>
              <span className="text-gray-300">{airQuality.status}</span>
            </div>
          )}
          {traffic && (
            <div
              className="backdrop-blur-sm rounded-full px-3 py-1.5 text-xs flex items-center gap-2"
              style={{
                background: congestionColor(traffic.congestion_level) + "22",
                border: `1px solid ${congestionColor(traffic.congestion_level)}66`,
              }}
            >
              <span style={{ color: congestionColor(traffic.congestion_level) }}>
                🚗 {traffic.congestion_percentage}%
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
