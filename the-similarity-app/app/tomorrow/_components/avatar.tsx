export function Avatar({ initials = "K" }: { initials?: string }) {
  return <span className="tomorrow-avatar">{initials}</span>;
}

