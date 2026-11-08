import { createFileRoute } from "@tanstack/react-router";
import { AuthForm } from "@/components/AuthForm";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Log in · Quad" },
      { name: "description", content: "Log in to Quad." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: () => <AuthForm mode="login" />,
});
