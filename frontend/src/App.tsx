import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router";
import { get, type Status } from "./api";
import Docs from "./Docs";
import Gate from "./Gate";
import Setup from "./Setup";

export default function App() {
  const [status, setStatus] = useState<Status | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    get<Status>("/api/status").then(setStatus, () => setFailed(true));
  }, []);

  if (failed) return <Gate title="Ohara can't be reached" body="The server didn't answer. Reload the page in a moment." />;
  if (!status) return null;

  return (
    <Routes>
      <Route path="/setup" element={status.configured ? <Navigate to="/" replace /> : <Setup url={status.url} installUrl={status.install_url} />} />
      <Route
        path="*"
        element={
          !status.configured ? (
            <Navigate to="/setup" replace />
          ) : status.allowed ? (
            <Docs status={status} />
          ) : (
            <Gate
              status={`${status.repo} is private`}
              title={status.user ? "You don't have access" : "Sign in to read the docs"}
              body={
                status.user
                  ? `Signed in as ${status.user.login}, who can't read ${status.repo} on GitHub. Ask a repository admin for access, then reload.`
                  : "Use a GitHub account that can read the repository. Your access follows GitHub: lose it there and you lose it here."
              }
              action={status.user ? "signOut" : "signIn"}
            />
          )
        }
      />
    </Routes>
  );
}
