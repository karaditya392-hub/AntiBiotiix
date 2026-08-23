import { useEffect, useState } from "react";
import { Route, Router, Switch, useLocation } from "wouter";
import { useHashLocation } from "wouter/use-hash-location";
import Landing from "@/pages/Landing";
import Console from "@/pages/Console";

/**
 * Routing is HASH-based on purpose.
 *
 * backend/app.py serves exactly one HTML route ("/") and mounts /static. It has no
 * SPA catch-all, and the brief forbids changing the backend, so a real path like
 * /review would 404 on a hard refresh. Hash routes ("/#/review") are all served by
 * the same "/" document, which keeps routing entirely on the frontend.
 */
function Shell() {
  const [location] = useLocation();
  const onConsole = location.startsWith("/review");

  // Once mounted, the console STAYS mounted.
  //
  // app.js holds its DOM references in module scope and its module is cached after
  // the first import, so if the console unmounted those references would point at
  // detached nodes and every handler would silently stop working on return. Keeping
  // it mounted and toggling visibility avoids that without touching app.js.
  const [consoleMounted, setConsoleMounted] = useState(false);
  useEffect(() => {
    if (onConsole) setConsoleMounted(true);
  }, [onConsole]);

  // The console stylesheet styles <body> directly; the landing page provides its
  // own full-viewport surface. This flag lets each own the page background.
  useEffect(() => {
    document.body.dataset.surface = onConsole ? "console" : "landing";
  }, [onConsole]);

  return (
    <>
      <div hidden={onConsole}>
        <Switch>
          <Route path="/" component={Landing} />
          <Route path="/review">{null}</Route>
          <Route>
            <Landing />
          </Route>
        </Switch>
      </div>
      {consoleMounted && (
        <div hidden={!onConsole} data-console-host="">
          <Console />
        </div>
      )}
    </>
  );
}

export default function App() {
  return (
    <Router hook={useHashLocation}>
      <Shell />
    </Router>
  );
}
