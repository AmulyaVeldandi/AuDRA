import React, { FormEvent, useMemo, useState } from "react";
import { SAMPLE_REPORTS } from "../utils/sampleData";

export interface ReportUploadProps {
  onSubmit: (reportText: string, patientId?: string) => Promise<void>;
  isLoading: boolean;
}

const MIN_CHARACTERS = 50;

export const ReportUpload: React.FC<ReportUploadProps> = ({ onSubmit, isLoading }) => {
  const [reportText, setReportText] = useState("");
  const [patientId, setPatientId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [selectedSampleId, setSelectedSampleId] = useState<string>("");

  const trimmedReport = useMemo(() => reportText.trim(), [reportText]);
  const characterCount = trimmedReport.length;
  const isValid = characterCount >= MIN_CHARACTERS;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!isValid || isLoading) {
      return;
    }

    setError(null);
    setSelectedSampleId("");
    try {
      await onSubmit(trimmedReport, patientId.trim() || undefined);
      setReportText("");
      setPatientId("");
    } catch (submissionError) {
      const message =
        submissionError instanceof Error
          ? submissionError.message
          : "Failed to process the report. Please try again.";
      setError(message);
    }
  };

  return (
    <form className="report-upload card" onSubmit={handleSubmit}>
      <h2>Submit Radiology Report</h2>
      <label htmlFor="sample-select" className="form-label">
        Load Sample
      </label>
      <select
        id="sample-select"
        className="form-input"
        value={selectedSampleId}
        disabled={isLoading}
        onChange={(event) => {
          const nextSampleId = event.target.value;
          setSelectedSampleId(nextSampleId);
          const sample = SAMPLE_REPORTS.find((item) => item.id === nextSampleId);
          if (sample) {
            setReportText(sample.text);
          }
        }}
      >
        <option value="">Select a sample report...</option>
        {SAMPLE_REPORTS.map((sample) => (
          <option key={sample.id} value={sample.id}>
            {sample.name}
          </option>
        ))}
      </select>

      <label htmlFor="report-text" className="form-label">
        Report Text
      </label>
      <textarea
        id="report-text"
        name="report-text"
        rows={12}
        className="form-textarea"
        placeholder="Paste the radiology report text here..."
        value={reportText}
        onChange={(event) => setReportText(event.target.value)}
        disabled={isLoading}
      />
      <div className={`character-count ${isValid ? "" : "text-error"}`}>
        {characterCount} / {MIN_CHARACTERS} characters
      </div>

      <label htmlFor="patient-id" className="form-label">
        Patient ID <span className="text-muted">(optional)</span>
      </label>
      <input
        id="patient-id"
        name="patient-id"
        type="text"
        className="form-input"
        placeholder="Enter patient identifier"
        value={patientId}
        onChange={(event) => setPatientId(event.target.value)}
        disabled={isLoading}
      />

      <button
        type="submit"
        className="primary-button"
        disabled={!isValid || isLoading}
        aria-disabled={!isValid || isLoading}
      >
        {isLoading ? (
          <span className="button-loading">
            <span className="spinner" aria-hidden="true" /> Processing...
          </span>
        ) : (
          "Process Report"
        )}
      </button>

      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
    </form>
  );
};
