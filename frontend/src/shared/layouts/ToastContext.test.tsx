import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider, useToast } from "./ToastContext";

function ToastHarness() {
  const { showToast } = useToast();
  return (
    <div>
      <button type="button" onClick={() => showToast({ message: "Refresh completed.", tone: "success" })}>Success</button>
      <button type="button" onClick={() => showToast({ message: "Refresh failed.", tone: "error" })}>Error</button>
    </div>
  );
}

describe("ToastProvider", () => {
  afterEach(() => vi.useRealTimers());

  it("renders one global top-level toast and auto-dismisses success", () => {
    vi.useFakeTimers();
    render(<ToastProvider><ToastHarness /></ToastProvider>);

    fireEvent.click(screen.getByRole("button", { name: "Success" }));
    expect(screen.getByRole("status")).toHaveTextContent("Refresh completed.");
    expect(screen.getByRole("status").parentElement).toHaveClass("global-toast-viewport");

    act(() => vi.advanceTimersByTime(4000));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("keeps errors until explicitly dismissed", () => {
    vi.useFakeTimers();
    render(<ToastProvider><ToastHarness /></ToastProvider>);

    fireEvent.click(screen.getByRole("button", { name: "Error" }));
    act(() => vi.advanceTimersByTime(10000));
    expect(screen.getByRole("alert")).toHaveTextContent("Refresh failed.");
    fireEvent.click(screen.getByRole("button", { name: "Dismiss notification" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
