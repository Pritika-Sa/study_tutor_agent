import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import QuizQuestion from "./QuizQuestion";

const question = {
  question_id: "q1",
  question: "What does normalization primarily reduce?",
  options: ["Redundancy", "Index size", "Network latency", "Page faults"],
  citation: { source: "OTHER", subject: "DBMS", chapter: "Normalization", page: 1 },
  // Deliberately no `correct_option` -- matches the real backend contract.
};

describe("QuizQuestion", () => {
  it("renders every option with a positional letter (A, B, C, D)", () => {
    render(<QuizQuestion question={question} index={0} selectedAnswer={null} onSelect={() => {}} />);
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
    expect(screen.getByText("C")).toBeInTheDocument();
    expect(screen.getByText("D")).toBeInTheDocument();
    expect(screen.getByText("Redundancy")).toBeInTheDocument();
  });

  it("never renders a correct answer indicator, even though a citation is shown", () => {
    render(<QuizQuestion question={question} index={0} selectedAnswer={null} onSelect={() => {}} />);
    expect(screen.queryByText(/correct/i)).not.toBeInTheDocument();
  });

  it("calls onSelect with the question id and the clicked option's letter", () => {
    const onSelect = vi.fn();
    render(<QuizQuestion question={question} index={0} selectedAnswer={null} onSelect={onSelect} />);

    fireEvent.click(screen.getByLabelText(/Index size/));

    expect(onSelect).toHaveBeenCalledWith("q1", "B");
  });

  it("marks the selected option as checked", () => {
    render(<QuizQuestion question={question} index={0} selectedAnswer="C" onSelect={() => {}} />);
    expect(screen.getByLabelText(/Network latency/)).toBeChecked();
    expect(screen.getByLabelText(/Redundancy/)).not.toBeChecked();
  });
});
