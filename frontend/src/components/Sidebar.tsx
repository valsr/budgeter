import { NavLink } from "react-router-dom";

const NAV_ITEMS = [
  {
    to: "/",
    label: "Overview",
    end: true,
    icon: (
      <svg viewBox="0 0 24 24">
        <rect x="3.5" y="3.5" width="8" height="8" rx="1.5" />
        <rect x="14.5" y="3.5" width="6" height="5" rx="1.5" />
        <rect x="14.5" y="11" width="6" height="9.5" rx="1.5" />
        <rect x="3.5" y="14" width="8" height="6.5" rx="1.5" />
      </svg>
    ),
  },
  {
    to: "/accounts",
    label: "Accounts",
    icon: (
      <svg viewBox="0 0 24 24">
        <path d="M3 9.5L12 4l9 5.5" />
        <path d="M4.5 9.5v9M9 9.5v9M15 9.5v9M19.5 9.5v9" />
        <path d="M3 18.5h18" />
      </svg>
    ),
  },
  {
    to: "/transactions",
    label: "Transactions",
    icon: (
      <svg viewBox="0 0 24 24">
        <path d="M4 8h14" />
        <path d="M15 5l3 3-3 3" />
        <path d="M20 16H6" />
        <path d="M9 13l-3 3 3 3" />
      </svg>
    ),
  },
  {
    to: "/budgets",
    label: "Budgets",
    icon: (
      <svg viewBox="0 0 24 24">
        <circle cx="11" cy="12" r="8" />
        <path d="M11 4v8h8" />
      </svg>
    ),
  },
  {
    to: "/import",
    label: "Import",
    icon: (
      <svg viewBox="0 0 24 24">
        <path d="M12 15V4" />
        <path d="M8 8l4-4 4 4" />
        <path d="M4 16v4h16v-4" />
      </svg>
    ),
  },
  {
    to: "/settings",
    label: "Settings",
    icon: (
      <svg viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="3" />
        <path d="M12 2.5v2.6M12 18.9v2.6M4.2 4.2l1.8 1.8M18 18l1.8 1.8M2.5 12h2.6M18.9 12h2.6M4.2 19.8L6 18M18 6l1.8-1.8" />
      </svg>
    ),
  },
];

export function Sidebar() {
  return (
    <div className="sidebar">
      <div className="brand">
        Finance
        <span>local · single user</span>
      </div>
      {NAV_ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) => "nav-item" + (isActive ? " active" : "")}
        >
          {item.icon}
          <span>{item.label}</span>
        </NavLink>
      ))}
    </div>
  );
}
