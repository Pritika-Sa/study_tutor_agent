import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ProtectedRoute from "./ProtectedRoute";

const mockUseAuth = vi.fn();
vi.mock("../context/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

function renderProtected(initialPath = "/dashboard") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/login" element={<div>Login Page</div>} />
        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<div>Dashboard Content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

describe("ProtectedRoute", () => {
  it("shows a loading state while the session is being restored", () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: false, loading: true });
    renderProtected();
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByText("Dashboard Content")).not.toBeInTheDocument();
  });

  it("redirects unauthenticated users to /login instead of rendering protected content", () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: false, loading: false });
    renderProtected();
    expect(screen.getByText("Login Page")).toBeInTheDocument();
    expect(screen.queryByText("Dashboard Content")).not.toBeInTheDocument();
  });

  it("renders protected content for authenticated users", () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: true, loading: false });
    renderProtected();
    expect(screen.getByText("Dashboard Content")).toBeInTheDocument();
  });
});
