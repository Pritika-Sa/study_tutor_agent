import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useTrack } from "../context/TrackContext";

const LINKS = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/tutor", label: "Tutor" },
  { to: "/quiz", label: "Quiz" },
  { to: "/progress", label: "Progress" },
  { to: "/weak-topics", label: "Weak Topics" },
  { to: "/revision-plan", label: "Revision" },
];

function linkClass({ isActive }) {
  return isActive ? "navbar__link navbar__link--active" : "navbar__link";
}

export default function Navbar() {
  const { user, logout } = useAuth();
  const { track } = useTrack();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  function handleNavigate() {
    setMenuOpen(false);
  }

  return (
    <header className={`navbar${menuOpen ? " navbar--open" : ""}`}>
      <div className="navbar__inner">
        <NavLink to="/dashboard" className="navbar__brand" onClick={handleNavigate}>
          <span className="navbar__brand-mark" aria-hidden="true">
            AT
          </span>
          Adaptive Study Tutor
        </NavLink>

        <nav className="navbar__links" aria-label="Main navigation">
          {LINKS.map((link) => (
            <NavLink key={link.to} to={link.to} className={linkClass} onClick={handleNavigate}>
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="navbar__meta">
          {track && (
            <NavLink to="/track-selection" className="navbar__track" title="Change track">
              {track}
            </NavLink>
          )}
          {user && <span className="navbar__user">{user.name}</span>}
          <button type="button" className="btn btn--small btn--ghost" onClick={handleLogout}>
            Logout
          </button>
          <button
            type="button"
            className="navbar__toggle"
            aria-label={menuOpen ? "Close navigation menu" : "Open navigation menu"}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span className="navbar__toggle-bar" />
          </button>
        </div>
      </div>
    </header>
  );
}
