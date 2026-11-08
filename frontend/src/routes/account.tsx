import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { genderLabel, useAuth } from "@/lib/auth";
import { topicLabel } from "@/lib/events";

export const Route = createFileRoute("/account")({
  head: () => ({
    meta: [
      { title: "Your account · Quad" },
      { name: "description", content: "Your Quad profile." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: Account,
});

const formatBirthday = (b: string) =>
  new Date(`${b}T00:00`).toLocaleDateString("en-CA", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

function Account() {
  const { user, ready, logout } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (ready && !user) void navigate({ to: "/login" });
  }, [ready, user, navigate]);

  if (!ready || !user)
    return (
      <main className="mx-auto max-w-xl px-4 py-20 text-center text-muted-foreground">
        Loading…
      </main>
    );

  const rows: [string, string][] = [
    ["Email", user.email],
    ["Birthday", user.birthday ? formatBirthday(user.birthday) : "Not shared"],
    ["Major", user.major ?? "Not shared"],
    ["Gender", genderLabel(user.gender, user.gender_detail)],
    ["Interests", user.interests.length ? user.interests.map(topicLabel).join(", ") : "None yet"],
    ["Hobbies", user.hobbies.length ? user.hobbies.join(", ") : "None yet"],
  ];

  return (
    <main className="mx-auto max-w-3xl px-4 pb-24 md:px-8">
      <section className="py-10 md:py-14">
        <h1 className="font-display text-4xl md:text-5xl">Your account</h1>
        <p className="mt-3 text-muted-foreground">
          Your interests shape the picks on Discover. Only you can see this page.
        </p>
      </section>

      {!user.onboarded && (
        <div className="panel mb-6 flex flex-wrap items-center justify-between gap-3">
          <p>You haven't finished setting up your profile.</p>
          <Link to="/setup" className="btn-solid">
            Finish setup
          </Link>
        </div>
      )}

      <dl className="panel divide-y divide-border p-0">
        {rows.map(([k, v]) => (
          <div key={k} className="grid grid-cols-3 gap-4 px-5 py-3">
            <dt className="eyebrow self-center">{k}</dt>
            <dd
              className={`col-span-2 ${v === "Not shared" || v === "None yet" ? "italic text-muted-foreground" : ""}`}
            >
              {v}
            </dd>
          </div>
        ))}
      </dl>

      <div className="mt-6 flex flex-wrap gap-2">
        <Link to="/setup" className="btn-solid">
          Edit profile
        </Link>
        <button
          type="button"
          className="btn-ghost"
          onClick={async () => {
            await logout();
            await navigate({ to: "/" });
          }}
        >
          Log out
        </button>
      </div>
    </main>
  );
}
