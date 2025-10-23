import React, { useState } from 'react';
import { GuidelineMatch } from './components/GuidelineMatch';
import { ReportViewer } from './components/ReportViewer';
import { TaskList } from './components/TaskList';

export const App: React.FC = () => {
  const [report] = useState('Sample radiology report');
  const [matches] = useState([
    { id: 'FLEISCHNER-2017-1', summary: 'Follow-up CT in 3 months' }
  ]);
  const [tasks] = useState([
    { title: 'Schedule CT', description: 'Book low-dose CT in 3 months' }
  ]);

  return (
    <main>
      <h1>AuDRA-Rad Dashboard</h1>
      <ReportViewer report={report} />
      <GuidelineMatch matches={matches} />
      <TaskList tasks={tasks} />
    </main>
  );
};
