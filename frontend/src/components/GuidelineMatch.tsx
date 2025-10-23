import React from 'react';

type GuidelineMatchProps = {
  matches: Array<{ id: string; summary: string }>;
};

export const GuidelineMatch: React.FC<GuidelineMatchProps> = ({ matches }) => (
  <section>
    <h2>Guideline Matches</h2>
    <ul>
      {matches.map((match) => (
        <li key={match.id}>
          <strong>{match.id}</strong>: {match.summary}
        </li>
      ))}
    </ul>
  </section>
);
