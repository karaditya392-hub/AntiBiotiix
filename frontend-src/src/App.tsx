import { useEffect, useState } from "react";
import { Route, Router, Switch, useLocation } from "wouter";
import { useHashLocation } from "wouter/use-hash-location";

import { AuthProvider } from "@/context/AuthContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import Login from "@/pages/Login";
import Landing from "@/pages/Landing";
import PatientTypeSelection from "@/pages/PatientTypeSelection";
import PatientFeedback from "@/pages/PatientFeedback";
import SelectReturningPatient from "@/pages/SelectReturningPatient";
import RegisterNewPatient from "@/pages/RegisterNewPatient";
import PatientProfile from "@/pages/PatientProfile";
import NewVisitEntry from "@/pages/NewVisitEntry";
import PrescriptionEntry from "@/pages/PrescriptionEntry";
import ClinicalSafetyAnalysis from "@/pages/ClinicalSafetyAnalysis";
import VisitSummary from "@/pages/VisitSummary";
import PatientMedicationHistory from "@/pages/PatientMedicationHistory";
import PatientHistoryAssistant from "@/pages/PatientHistoryAssistant";
import PatientDashboard from "@/pages/PatientDashboard";
import ClinicalToolsLanding from "@/pages/ClinicalToolsLanding";
import GuidelinesPage from "@/pages/GuidelinesPage";
import EvidencePage from "@/pages/EvidencePage";
import SafetyEnginePage from "@/pages/SafetyEnginePage";
import ReferencePage from "@/pages/ReferencePage";
import Console from "@/pages/Console";
import FeedbackAlerts from "@/components/FeedbackAlerts";

/**
 * Multi-Step Doctor Workflow Routing (Hash-Based).
 *
 * Initial Landing Page: / -> Landing
 * Patient Workflow:
 *   Page 1: /patient-type -> PatientTypeSelection (RETURNING PATIENT vs NEW PATIENT)
 *   Page 2A: /patients/returning -> SelectReturningPatient (Protected by OAuth Login)
 *   Page 2B: /patients/new -> RegisterNewPatient (Protected by OAuth Login)
 *   Page 3: /patients/:patient_id -> PatientProfile
 *   Page 4: /patients/:patient_id/visit/new -> NewVisitEntry
 *   Page 5: /patients/:patient_id/visits/:visit_id/prescription -> PrescriptionEntry
 *   Page 6: /patients/:patient_id/visits/:visit_id/analysis -> ClinicalSafetyAnalysis
 *   Page 7: /patients/:patient_id/visits/:visit_id/summary -> VisitSummary
 *
 * Additional Views:
 *   /login -> Login (OAuth Doctor Credential Verification)
 *   /clinical-tools and /clinical-tools/* -> Clinical Tools (Protected by OAuth Login)
 *   /patients/:patient_id/medications -> PatientMedicationHistory
 *   /patients/:patient_id/history-assistant -> PatientHistoryAssistant
 *   /dashboard -> PatientDashboard
 *   /review/console or /review/safety -> Console (Rule Engine / Guidelines Explorer)
 */
function Shell() {
  const [location] = useLocation();
  const onConsole = location.startsWith("/review/console") || location === "/review/safety";
  const consoleView = location === "/review/safety" ? "safety" : "entry";

  const [consoleMounted, setConsoleMounted] = useState(false);
  useEffect(() => {
    if (onConsole) setConsoleMounted(true);
  }, [onConsole]);

  useEffect(() => {
    document.body.dataset.surface = onConsole ? "console" : "landing";
  }, [onConsole]);

  return (
    <>
      <div hidden={onConsole}>
        <Switch>
          <Route path="/" component={Landing} />
          <Route path="/landing" component={Landing} />
          <Route path="/login" component={Login} />
          <Route path="/patient-type" component={PatientTypeSelection} />
          {/* PUBLIC on purpose: the patient has no login. Access is by the
              per-visit code, not by name - see PatientFeedback.tsx. */}
          <Route path="/feedback" component={PatientFeedback} />
          <Route path="/clinical-tools">
            {() => <ProtectedRoute component={ClinicalToolsLanding} path="/clinical-tools" />}
          </Route>
          <Route path="/clinical-tools/guidelines">
            {() => <ProtectedRoute component={GuidelinesPage} path="/clinical-tools/guidelines" />}
          </Route>
          <Route path="/clinical-tools/evidence">
            {() => <ProtectedRoute component={EvidencePage} path="/clinical-tools/evidence" />}
          </Route>
          <Route path="/clinical-tools/safety">
            {() => <ProtectedRoute component={SafetyEnginePage} path="/clinical-tools/safety" />}
          </Route>
          <Route path="/clinical-tools/reference">
            {() => <ProtectedRoute component={ReferencePage} path="/clinical-tools/reference" />}
          </Route>
          <Route path="/patients/returning">
            {() => <ProtectedRoute component={SelectReturningPatient} path="/patients/returning" />}
          </Route>
          <Route path="/patients/new">
            {() => <ProtectedRoute component={RegisterNewPatient} path="/patients/new" />}
          </Route>
          <Route path="/patients/:patient_id/visit/new" component={NewVisitEntry} />
          <Route path="/patients/:patient_id/visits/:visit_id/prescription" component={PrescriptionEntry} />
          <Route path="/patients/:patient_id/visits/:visit_id/analysis" component={ClinicalSafetyAnalysis} />
          <Route path="/patients/:patient_id/visits/:visit_id/summary" component={VisitSummary} />
          <Route path="/patients/:patient_id/medications" component={PatientMedicationHistory} />
          <Route path="/patients/:patient_id/history-assistant" component={PatientHistoryAssistant} />
          <Route path="/patients/:patient_id" component={PatientProfile} />
          <Route path="/dashboard" component={PatientDashboard} />
          <Route path="/review">{PatientTypeSelection}</Route>
          <Route>
            <Landing />
          </Route>
        </Switch>
      </div>

      {/* Patient follow-up alerts, mounted once outside the router so they reach
          the clinician on every page. Renders nothing signed out, and nothing
          until a response is 24 hours past its visit. */}
      <FeedbackAlerts />

      {consoleMounted && (
        <div hidden={!onConsole} data-console-host="">
          <Console view={consoleView} />
        </div>
      )}
    </>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Router hook={useHashLocation}>
        <Shell />
      </Router>
    </AuthProvider>
  );
}
