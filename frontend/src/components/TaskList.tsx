import React, { useMemo } from "react";
import { Calendar, ClipboardList } from "lucide-react";
import { format, parseISO } from "date-fns";

export interface Task {
  task_id: string;
  procedure: string;
  scheduled_date: string;
  reason: string;
  order_id?: string;
}

export interface TaskListProps {
  tasks: Task[];
}

const formatScheduledDate = (isoDate: string): string => {
  try {
    return format(parseISO(isoDate), "MMM d, yyyy");
  } catch {
    return isoDate;
  }
};

export const TaskList: React.FC<TaskListProps> = ({ tasks }) => {
  const sortedTasks = useMemo(
    () =>
      [...tasks].sort((a, b) => {
        const first = new Date(a.scheduled_date).getTime();
        const second = new Date(b.scheduled_date).getTime();
        return first - second;
      }),
    [tasks]
  );

  if (!sortedTasks.length) {
    return (
      <section
        style={{
          backgroundColor: "#ffffff",
          borderRadius: "16px",
          border: "1px solid #e2e8f0",
          padding: "24px",
          textAlign: "center",
          color: "#94a3b8",
        }}
      >
        No follow-up tasks created.
      </section>
    );
  }

  return (
    <section
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "18px",
      }}
    >
      {sortedTasks.map((task) => (
        <article
          key={task.task_id}
          style={{
            backgroundColor: "#ffffff",
            borderRadius: "18px",
            border: "1px solid #e2e8f0",
            padding: "20px",
            boxShadow: "0 12px 30px rgba(15, 23, 42, 0.06)",
            display: "grid",
            gap: "10px",
          }}
        >
          <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <h3
              style={{
                margin: 0,
                color: "#0f172a",
                fontSize: "1.05rem",
              }}
            >
              {task.procedure}
            </h3>
            {task.order_id && (
              <span
                style={{
                  padding: "4px 10px",
                  borderRadius: "999px",
                  backgroundColor: "#e0e7ff",
                  color: "#3730a3",
                  fontSize: "0.75rem",
                  fontWeight: 700,
                  letterSpacing: "0.05em",
                  textTransform: "uppercase",
                }}
              >
                Order #{task.order_id}
              </span>
            )}
          </header>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", color: "#475569" }}>
            <Calendar size={18} />
            <span style={{ fontWeight: 600 }}>{formatScheduledDate(task.scheduled_date)}</span>
          </div>
          <div style={{ display: "flex", alignItems: "flex-start", gap: "10px", color: "#64748b" }}>
            <ClipboardList size={18} />
            <p style={{ margin: 0, lineHeight: 1.5 }}>{task.reason}</p>
          </div>
        </article>
      ))}
    </section>
  );
};
