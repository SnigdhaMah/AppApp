"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

interface App {
  title: string;
  logo: string;
  link: string;
  color?: string;
  icon?: React.ReactNode;
  locked?: boolean;
}

const StudioIcon = () => (
  <svg width="52" height="52" viewBox="0 0 52 52" fill="none">
    <path d="M26 10V42" stroke="white" strokeWidth="5" strokeLinecap="round"/>
    <path d="M10 26H42" stroke="white" strokeWidth="5" strokeLinecap="round"/>
  </svg>
);

const CoffeeIcon = () => (
  <svg width="52" height="52" viewBox="0 0 52 52" fill="none">
    <path d="M10 18h24v18a8 8 0 01-8 8H18a8 8 0 01-8-8V18z" fill="#1a1a2e" opacity="0.9"/>
    <path d="M34 22h4a4 4 0 010 8h-4" stroke="#1a1a2e" strokeWidth="3" strokeLinecap="round" opacity="0.8"/>
    <path d="M16 12c0-3 4-3 4-6" stroke="white" strokeWidth="2" strokeLinecap="round" opacity="0.7"/>
    <path d="M22 12c0-3 4-3 4-6" stroke="white" strokeWidth="2" strokeLinecap="round" opacity="0.5"/>
    <path d="M12 44h20" stroke="#1a1a2e" strokeWidth="3" strokeLinecap="round"/>
  </svg>
);

const LockIcon = () => (
  <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
    <rect x="7" y="16" width="22" height="16" rx="4" fill="white" opacity="0.15"/>
    <path d="M12 16v-4a6 6 0 0112 0v4" stroke="white" strokeWidth="2.5" strokeLinecap="round" opacity="0.25"/>
    <circle cx="18" cy="24" r="2.5" fill="white" opacity="0.2"/>
  </svg>
);

const STATIC_APPS: App[] = [
  {
    title: "App²  Studio",
    logo: "",
    link: "/studio",
    color: "linear-gradient(135deg, #e8734a 0%, #c0392b 100%)",
    icon: <StudioIcon />,
  },
  {
    title: "Coffee Chatter",
    logo: "",
    link: "https://buildappsstack-appsbucket0b78b832-eptrkwrugpmp.s3.us-east-2.amazonaws.com/apps/01KKCW1N8A09VK1GN0R5ATYZSY/index.html",
    color: "linear-gradient(135deg, #e84adb 0%, #f1c3be 100%)",
    icon: <CoffeeIcon/>,
  },
  {
    title: "",
    logo: "",
    link: "#",
    color: "",
    icon: null,
  },
  {
    title: "",
    logo: "",
    link: "#",
    color: "",
    icon: null,
  },
];

export default function Dashboard() {
  const [apiError, setApiError] = useState<string | null>(null);
  const [apps, setApps] = useState<App[]>(STATIC_APPS);
  const [hovered, setHovered] = useState<number | null>(null);

  async function getApps() {
    setApiError(null);
    if (!API_BASE) return;
    try {
      const res = await fetch(`${API_BASE}/apps`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        const err = await res.text();
        setApiError(err || "Failed to fetch apps");
        return;
      }
      const data = await res.json();
    } catch {
      setApiError("Something went wrong.");
    }
  }

//   useEffect(() => { getApps(); }, []);

  const totalSlots = 12;
  const lockedCount = totalSlots - apps.length;

  return (
    <div style={styles.root}>
      {/* Grain overlay */}
      <div className="grain" aria-hidden="true" />

      {/* Orb glow */}
      <div className="orb" aria-hidden="true" />

      {/* Nav */}
      <nav className="nav">
        <div className="nav-logo" aria-label="App² logo">
          <img src="/logo.svg" alt="App² logo" width="36" height="36" />
        </div>
        <span style={styles.navBrand}>App<sup style={{fontSize:"0.6em"}}>2</sup></span>
      </nav>

      {/* Main */}
      <main style={styles.page}>
        {/* Liquid glass frame */}
        <div style={styles.glassFrame}>
          {/* Inner shimmer border */}
          <div style={styles.shimmerBorder} aria-hidden="true" />

          <h2 style={styles.heading}>Your Apps</h2>

          <div style={styles.grid}>
            {/* Real apps */}
            {apps.map((app, i) => (
              <Link
                key={app.title}
                href={app.link}
                style={{ textDecoration: "none" }}
              >
                <div
                  style={styles.appSlot}
                  onMouseEnter={() => setHovered(i)}
                  onMouseLeave={() => setHovered(null)}
                >
                  <div
                    style={{
                      ...styles.appIcon,
                      background: app.color,
                      transform: hovered === i ? "scale(1.08) translateY(-3px)" : "scale(1)",
                      boxShadow: hovered === i
                        ? `0 20px 50px ${app.color?.includes("e8734a") ? "rgba(232,115,74,0.5)" : "rgba(212,91,255,0.5)"}, 0 0 0 1px rgba(255,255,255,0.15)`
                        : "0 8px 24px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.08)",
                      transition: "all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)",
                    }}
                  >
                    {app.icon}
                    {/* Gloss overlay */}
                    <div style={styles.iconGloss} aria-hidden="true" />
                  </div>
                  <span style={styles.appLabel}>{app.title}</span>
                </div>
              </Link>
            ))}

            {/* Empty locked slots */}
            {Array.from({ length: lockedCount }).map((_, i) => (
              <div key={`locked-${i}`} style={styles.appSlot}>
                <div style={styles.lockedIcon}>
                  <LockIcon />
                </div>
              </div>
            ))}
          </div>
        </div>

        {apiError && (
          <p style={styles.error}>{apiError}</p>
        )}
      </main>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    minHeight: "100vh",
    background: "linear-gradient(160deg, #0d0d18 0%, #12101e 50%, #0a0d16 100%)",
    fontFamily: "'Sora', sans-serif",
    position: "relative",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
  },
  grain: {
    position: "fixed",
    inset: "-200%",
    width: "400%",
    height: "400%",
    backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.04'/%3E%3C/svg%3E")`,
    animation: "grain 0.8s steps(1) infinite",
    pointerEvents: "none",
    zIndex: 0,
    opacity: 0.6,
  },
  orbTopRight: {
    position: "fixed",
    top: "-10%",
    right: "-5%",
    width: "55vw",
    height: "55vw",
    borderRadius: "50%",
    background: "radial-gradient(circle, rgba(180,60,40,0.35) 0%, rgba(120,30,20,0.15) 50%, transparent 70%)",
    filter: "blur(60px)",
    animation: "orbPulse 6s ease-in-out infinite",
    pointerEvents: "none",
    zIndex: 0,
  },
  orbBottomLeft: {
    position: "fixed",
    bottom: "-15%",
    left: "-10%",
    width: "50vw",
    height: "50vw",
    borderRadius: "50%",
    background: "radial-gradient(circle, rgba(100,40,160,0.25) 0%, rgba(60,20,100,0.1) 50%, transparent 70%)",
    filter: "blur(80px)",
    animation: "orbPulse 8s ease-in-out infinite reverse",
    pointerEvents: "none",
    zIndex: 0,
  },
  nav: {
    position: "relative",
    zIndex: 10,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "20px 32px",
  },
  navLogo: {
    display: "flex",
    alignItems: "center",
  },
  navBrand: {
    color: "rgba(255,255,255,0.8)",
    fontSize: "1.25rem",
    fontWeight: 600,
    letterSpacing: "0.02em",
  },
  page: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: "20px",
    position: "relative",
    zIndex: 10,
  },
  glassFrame: {
    position: "relative",
    width: "min(820px, 96vw)",
    background: "rgba(255,255,255,0.055)",
    backdropFilter: "blur(40px) saturate(180%)",
    WebkitBackdropFilter: "blur(40px) saturate(180%)",
    borderRadius: "28px",
    border: "1px solid rgba(255,255,255,0.12)",
    padding: "52px 52px 52px",
    boxShadow: `
      0 0 0 1px rgba(255,255,255,0.05) inset,
      0 40px 80px rgba(0,0,0,0.5),
      0 0 120px rgba(180,60,40,0.08)
    `,
    overflow: "hidden",
  },
  shimmerBorder: {
    position: "absolute",
    inset: 0,
    borderRadius: "28px",
    background: "linear-gradient(135deg, rgba(255,255,255,0.12) 0%, transparent 40%, transparent 60%, rgba(255,255,255,0.06) 100%)",
    pointerEvents: "none",
    animation: "shimmer 4s ease-in-out infinite",
  },
  heading: {
    color: "rgba(255,255,255,0.92)",
    fontSize: 90,
    fontWeight: 10,
    textAlign: "center",
    marginBottom: "44px",
    // textShadow: "0 2px 20px rgba(0,0,0,0.4)",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(4, 1fr)",
    gap: "24px 20px",
  },
  appSlot: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "12px",
    cursor: "pointer",
  },
  appIcon: {
    width: "120px",
    height: "120px",
    borderRadius: "24px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    position: "relative",
    overflow: "hidden",
  },
  iconGloss: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    height: "50%",
    background: "linear-gradient(180deg, rgba(255,255,255,0.18) 0%, transparent 100%)",
    borderRadius: "24px 24px 0 0",
    pointerEvents: "none",
  },
  lockedIcon: {
    width: "120px",
    height: "120px",
    borderRadius: "24px",
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.07)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    backdropFilter: "blur(8px)",
  },
  appLabel: {
    color: "rgba(255,255,255,0.75)",
    fontSize: "0.78rem",
    fontWeight: 400,
    letterSpacing: "0.01em",
    textAlign: "center",
    maxWidth: "110px",
    lineHeight: 1.3,
  },
  error: {
    marginTop: "16px",
    color: "rgba(255,120,100,0.8)",
    fontSize: "0.85rem",
    textAlign: "center",
  },
};