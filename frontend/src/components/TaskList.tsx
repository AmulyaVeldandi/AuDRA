import React from 'react';

type TaskListProps = {
  tasks: Array<{ title: string; description: string }>;
};

export const TaskList: React.FC<TaskListProps> = ({ tasks }) => (
  <section>
    <h2>Follow-up Tasks</h2>
    <ol>
      {tasks.map((task) => (
        <li key={task.title}>
          <strong>{task.title}</strong>: {task.description}
        </li>
      ))}
    </ol>
  </section>
);
