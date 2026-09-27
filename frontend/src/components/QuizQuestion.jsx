import { optionLetter } from "../utils/formatters";
import CitationBadge from "./CitationBadge";

// SECURITY NOTE: `question` (the backend's public quiz payload) never
// contains `correct_option` -- this component has no code path that could
// display one even if it were present, and nothing here writes an answer
// key to localStorage. Only the student's own selected letter lives in
// this component's parent state, never the correctness of that letter.
export default function QuizQuestion({ question, index, selectedAnswer, onSelect }) {
  return (
    <fieldset className="quiz-question">
      <legend className="quiz-question__title">
        Question {index + 1}: {question.question}
      </legend>
      <div className="quiz-question__options">
        {question.options.map((option, i) => {
          const letter = optionLetter(i);
          const inputId = `${question.question_id}-${letter}`;
          const isSelected = selectedAnswer === letter;
          return (
            <label
              key={inputId}
              htmlFor={inputId}
              className={`quiz-option${isSelected ? " quiz-option--selected" : ""}`}
            >
              <input
                type="radio"
                id={inputId}
                name={question.question_id}
                value={letter}
                checked={isSelected}
                onChange={() => onSelect(question.question_id, letter)}
              />
              <span className="quiz-option__letter">{letter}</span>
              <span className="quiz-option__text">{option}</span>
            </label>
          );
        })}
      </div>
      {question.citation && (
        <div className="quiz-question__citation">
          <CitationBadge citation={question.citation} />
        </div>
      )}
    </fieldset>
  );
}
