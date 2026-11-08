import { createFileRoute } from "@tanstack/react-router";
import { AuthForm } from "@/components/AuthForm";

export const Route = createFileRoute("/signup")({
  head: () => ({
    meta: [
      { title: "Make an account · Quad" },
      {
        name: "description",
        content: "Create a Quad account to get UBC event picks based on your interests.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: () => <AuthForm mode="signup" />,
});
