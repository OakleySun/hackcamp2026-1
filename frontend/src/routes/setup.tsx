import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { ArrowLeft, Check, Plus, X } from "lucide-react";
import { TOPICS, type Topic } from "@/lib/events";
import { GENDERS, useAuth, type Gender, type Profile } from "@/lib/auth";

export const Route = createFileRoute("/setup")({
  head: () => ({
    meta: [
      { title: "Set up your account · Quad" },
      { name: "description", content: "Tell Quad a little about you to get better event picks." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: Setup,
});

const MAJORS = [
  "Arts (undeclared)",
  "Biology",
  "Business (Commerce)",
  "Chemistry",
  "Cognitive Systems",
  "Computer Science",
  "Economics",
  "Engineering",
  "English",
  "Environmental Sciences",
  "Geography",
  "History",
  "Kinesiology",
  "Land and Food Systems",
  "Mathematics",
  "Media Studies",
  "Microbiology",
  "Music",
  "Nursing",
  "Philosophy",
  "Physics",
  "Political Science",
  "Psychology",
  "Science (undeclared)",
  "Sociology",
  "Statistics",
  "Visual Arts",
];
const HOBBY_SUGGESTIONS = [
  "Hiking",
  "Gaming",
  "Cooking",
  "Photography",
  "Reading",
  "Running",
  "Music",
  "Drawing",
  "Dancing",
  "Volunteering",
  "Climbing",
  "Board games",
  "Coding",
  "Film",
  "Fashion",
  "Writing",
];
const MAX_HOBBIES = 12;
const MIN_AGE = 13;

const STEPS = ["birthday", "major", "gender", "interests", "hobbies"] as const;
type Step = (typeof STEPS)[number];

const QUESTIONS: Record<Step, { title: string; why: string; optional: boolean }> = {
  birthday: {
    title: "When's your birthday?",
    why: "Some events are 19+. We never show your birthday to anyone.",
    optional: true,
  },
  major: {
    title: "What are you studying?",
    why: "We'll flag talks and socials from your faculty.",
    optional: true,
  },
  gender: {
    title: "How do you identify?",
    why: "Helps us surface groups and events you might want to know about. Totally optional.",
    optional: true,
  },
  interests: {
    title: "What are you into?",
    why: "These set your picks on Discover. Choose as many as you like.",
    optional: false,
  },
  hobbies: {
    title: "Any hobbies?",
    why: "Add a few things you do for fun. Pick from the list or type your own.",
    optional: true,
  },
};

function ageOn(birthday: string, today = new Date()) {
  const b = new Date(`${birthday}T00:00`);
  const had =
    today.getMonth() > b.getMonth() ||
    (today.getMonth() === b.getMonth() && today.getDate() >= b.getDate());
  return today.getFullYear() - b.getFullYear() - (had ? 0 : 1);
}

const EMPTY: Profile = {
  birthday: null,
  major: null,
  gender: null,
  gender_detail: null,
  interests: [],
  hobbies: [],
};

function Setup() {
  const { user, ready, saveProfile } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [p, setP] = useState<Profile>(EMPTY);
  const [hobbyDraft, setHobbyDraft] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!ready) return;
    if (!user) void navigate({ to: "/signup" });
    // Editing later starts from the saved answers.
    else
      setP({
        birthday: user.birthday,
        major: user.major,
        gender: user.gender,
        gender_detail: user.gender_detail,
        interests: user.interests,
        hobbies: user.hobbies,
      });
  }, [ready, user?.user_id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!ready || !user)
    return (
      <main className="mx-auto max-w-xl px-4 py-20 text-center text-muted-foreground">
        Loading…
      </main>
    );

  const key = STEPS[step]!;
  const q = QUESTIONS[key];
  const last = step === STEPS.length - 1;
  const set = (patch: Partial<Profile>) => {
    setError("");
    setP((prev) => ({ ...prev, ...patch }));
  };

  const problem = (): string => {
    if (key === "birthday" && p.birthday) {
      const age = ageOn(p.birthday);
      if (new Date(`${p.birthday}T00:00`) > new Date() || age > 120)
        return "Enter a real birthday.";
      if (age < MIN_AGE) return `You need to be at least ${MIN_AGE} to use Quad.`;
    }
    if (key === "interests" && !p.interests.length) return "Pick at least one interest.";
    return "";
  };

  const next = async (skip = false) => {
    const answer = skip ? clear(key) : {};
    const draft = { ...p, ...answer };
    if (!skip) {
      const msg = problem();
      if (msg) return setError(msg);
    }
    setP(draft);
    setError("");
    if (!last) return setStep(step + 1);
    setSaving(true);
    try {
      await saveProfile(draft);
      await navigate({ to: "/" });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save your profile.");
    } finally {
      setSaving(false);
    }
  };

  const addHobby = (h: string) => {
    const v = h.replace(/\s+/g, " ").trim().slice(0, 40);
    if (
      !v ||
      p.hobbies.length >= MAX_HOBBIES ||
      p.hobbies.some((x) => x.toLowerCase() === v.toLowerCase())
    )
      return;
    set({ hobbies: [...p.hobbies, v] });
    setHobbyDraft("");
  };

  return (
    <main className="mx-auto max-w-xl px-4 pb-24 md:px-8">
      <div className="pt-10">
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            Step {step + 1} of {STEPS.length}
          </span>
          {user.onboarded && (
            <button
              type="button"
              className="underline"
              onClick={() => void navigate({ to: "/account" })}
            >
              Cancel
            </button>
          )}
        </div>
        <div
          className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-valuemin={1}
          aria-valuemax={STEPS.length}
          aria-valuenow={step + 1}
          aria-label="Setup progress"
        >
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${((step + 1) / STEPS.length) * 100}%` }}
          />
        </div>
      </div>

      <form
        className="panel mt-8 space-y-6"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          void next();
        }}
      >
        <div>
          <h1 className="font-display text-3xl md:text-4xl">{q.title}</h1>
          <p className="mt-2 text-muted-foreground">{q.why}</p>
        </div>

        {key === "birthday" && (
          <div>
            <label htmlFor="birthday" className="eyebrow mb-2 block">
              Birthday
            </label>
            <input
              id="birthday"
              type="date"
              className="field"
              value={p.birthday ?? ""}
              max={new Date().toISOString().slice(0, 10)}
              onChange={(e) => set({ birthday: e.target.value || null })}
            />
          </div>
        )}

        {key === "major" && (
          <div>
            <label htmlFor="major" className="eyebrow mb-2 block">
              Major or program
            </label>
            <input
              id="major"
              list="majors"
              className="field"
              placeholder="Start typing, e.g. Computer Science"
              maxLength={80}
              value={p.major ?? ""}
              onChange={(e) => set({ major: e.target.value || null })}
            />
            <datalist id="majors">
              {MAJORS.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </div>
        )}

        {key === "gender" && (
          <fieldset>
            <legend className="sr-only">Gender</legend>
            <div role="radiogroup" className="grid gap-2">
              {GENDERS.map((g) => {
                const on = p.gender === g.key;
                return (
                  <button
                    key={g.key}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    data-on={on}
                    className="chip chip-square justify-between py-2.5"
                    onClick={() =>
                      set({
                        gender: g.key as Gender,
                        gender_detail: g.key === "self-describe" ? p.gender_detail : null,
                      })
                    }
                  >
                    {g.label}
                    {on && <Check className="size-4" aria-hidden />}
                  </button>
                );
              })}
            </div>
            {p.gender === "self-describe" && (
              <div className="mt-4">
                <label htmlFor="gender-detail" className="eyebrow mb-2 block">
                  In your own words
                </label>
                <input
                  id="gender-detail"
                  className="field"
                  maxLength={40}
                  value={p.gender_detail ?? ""}
                  onChange={(e) => set({ gender_detail: e.target.value || null })}
                />
              </div>
            )}
          </fieldset>
        )}

        {key === "interests" && (
          <fieldset>
            <legend className="sr-only">Interests</legend>
            <div className="flex flex-wrap gap-2">
              {TOPICS.map((t) => {
                const on = p.interests.includes(t.slug);
                return (
                  <button
                    key={t.slug}
                    type="button"
                    aria-pressed={on}
                    className="chip"
                    data-on={on}
                    onClick={() =>
                      set({
                        interests: on
                          ? p.interests.filter((x) => x !== t.slug)
                          : [...p.interests, t.slug as Topic],
                      })
                    }
                  >
                    {on && <Check className="size-3.5" aria-hidden />}
                    {t.label}
                  </button>
                );
              })}
            </div>
          </fieldset>
        )}

        {key === "hobbies" && (
          <div className="space-y-4">
            {p.hobbies.length > 0 && (
              <ul className="flex flex-wrap gap-2" aria-label="Your hobbies">
                {p.hobbies.map((h) => (
                  <li key={h}>
                    <button
                      type="button"
                      className="chip"
                      data-on="true"
                      aria-label={`Remove ${h}`}
                      onClick={() => set({ hobbies: p.hobbies.filter((x) => x !== h) })}
                    >
                      {h}
                      <X className="size-3.5" aria-hidden />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex gap-2">
              <label htmlFor="hobby" className="sr-only">
                Add a hobby
              </label>
              <input
                id="hobby"
                className="field"
                placeholder="Type a hobby and press Enter"
                maxLength={40}
                value={hobbyDraft}
                disabled={p.hobbies.length >= MAX_HOBBIES}
                onChange={(e) => setHobbyDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && hobbyDraft.trim()) {
                    e.preventDefault();
                    addHobby(hobbyDraft);
                  }
                }}
              />
              <button
                type="button"
                className="btn-ghost shrink-0"
                onClick={() => addHobby(hobbyDraft)}
                disabled={!hobbyDraft.trim()}
              >
                <Plus className="size-4" aria-hidden />
                Add
              </button>
            </div>
            <div>
              <p className="eyebrow mb-2">Suggestions</p>
              <div className="flex flex-wrap gap-2">
                {HOBBY_SUGGESTIONS.filter(
                  (h) => !p.hobbies.some((x) => x.toLowerCase() === h.toLowerCase()),
                ).map((h) => (
                  <button
                    key={h}
                    type="button"
                    className="chip"
                    onClick={() => addHobby(h)}
                    disabled={p.hobbies.length >= MAX_HOBBIES}
                  >
                    <Plus className="size-3.5" aria-hidden />
                    {h}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2 border-t border-border pt-5">
          {step > 0 && (
            <button
              type="button"
              className="btn-ghost"
              onClick={() => {
                setError("");
                setStep(step - 1);
              }}
            >
              <ArrowLeft className="size-4" aria-hidden />
              Back
            </button>
          )}
          <div className="ml-auto flex gap-2">
            {q.optional && (
              <button
                type="button"
                className="btn-ghost"
                onClick={() => void next(true)}
                disabled={saving}
              >
                Skip
              </button>
            )}
            <button type="submit" className="btn-solid" disabled={saving}>
              {saving ? "Saving…" : last ? "Finish" : "Continue"}
            </button>
          </div>
        </div>
      </form>
    </main>
  );
}

/** Skipping a question clears its answer. */
function clear(step: Step): Partial<Profile> {
  switch (step) {
    case "birthday":
      return { birthday: null };
    case "major":
      return { major: null };
    case "gender":
      return { gender: null, gender_detail: null };
    case "hobbies":
      return { hobbies: [] };
    default:
      return {};
  }
}
