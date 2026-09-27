import { Outlet } from "react-router-dom";
import Navbar from "./Navbar";

// Shared chrome for every authenticated page -- keeps Navbar out of
// Login/Register, which render standalone.
export default function AppLayout() {
  return (
    <div className="app-layout">
      <Navbar />
      <main className="app-layout__content">
        <Outlet />
      </main>
    </div>
  );
}
