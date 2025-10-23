import React from 'react';

type ReportViewerProps = {
  report: string;
};

export const ReportViewer: React.FC<ReportViewerProps> = ({ report }) => (
  <section>
    <h2>Report</h2>
    <pre>{report}</pre>
  </section>
);
