import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AuthProvider, useAuth } from "./AuthContext";
import * as authApi from "../api/authApi";

vi.mock("../api/authApi");

function TestConsumer() {
  const { isAuthenticated, user, loading, login, logout } = useAuth();
  if (loading) return <div>loading</div>;
  return (
    <div>
      <div data-testid="auth-state">{isAuthenticated ? "authenticated" : "anonymous"}</div>
      <div data-testid="user-name">{user?.name || "none"}</div>
      <button onClick={() => login("student@example.com", "password123")}>login</button>
      <button onClick={() => logout()}>logout</button>
    </div>
  );
}

describe("AuthContext", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    authApi.fetchCurrentUser.mockRejectedValue({ response: { status: 401 } });
  });

  it("starts unauthenticated when no token is stored", async () => {
    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("auth-state")).toHaveTextContent("anonymous"));
  });

  it("becomes authenticated after a successful login, storing the token and user", async () => {
    authApi.loginUser.mockResolvedValue({
      data: { access_token: "fake-jwt-token", token_type: "bearer", user: { id: 1, name: "Test Student", email: "student@example.com" } },
    });

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("auth-state")).toHaveTextContent("anonymous"));
    fireEvent.click(screen.getByText("login"));

    await waitFor(() => expect(screen.getByTestId("auth-state")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("user-name")).toHaveTextContent("Test Student");
    expect(localStorage.getItem("auth_token")).toBe("fake-jwt-token");
  });

  it("clears stored state on logout", async () => {
    authApi.loginUser.mockResolvedValue({
      data: { access_token: "fake-jwt-token", token_type: "bearer", user: { id: 1, name: "Test Student", email: "student@example.com" } },
    });

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("auth-state")).toHaveTextContent("anonymous"));
    fireEvent.click(screen.getByText("login"));
    await waitFor(() => expect(screen.getByTestId("auth-state")).toHaveTextContent("authenticated"));

    fireEvent.click(screen.getByText("logout"));
    await waitFor(() => expect(screen.getByTestId("auth-state")).toHaveTextContent("anonymous"));
    expect(localStorage.getItem("auth_token")).toBeNull();
  });
});
