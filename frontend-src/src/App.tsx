import { useEffect, useState } from "react";
import { Route, Router, Switch, useLocation } from "wouter";
import { useHashLocation } from "wouter/use-hash-location";

import Landing from "@/pages/Landing";
import PatientTypeSelection from "@/pages/PatientTypeSelection";
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

/**
 * Multi-Step Doctor Workflow Routing (Hash-Based).
 *
 * Initial Landing Page: / -> Landing
 * Patient Workflow:
 *   Page 1: /patient-type -> PatientTypeSelection (RETURNING PATIENT vs NEW PATIENT)
 *   Page 2A: /patients/returning -> SelectReturningPatient
 *   Page 2B: /patients/new -> RegisterNewPatient
 *   Page 3: /patients/:patient_id -> PatientProfile
 *   Page 4: /patients/:patient_id/visit/new -> NewVisitEntry
 *   Page 5: /patients/:patient_id/visits/:visit_id/prescription -> PrescriptionEntry
 *   Page 6: /patients/:patient_id/visits/:visit_id/analysis -> ClinicalSafetyAnalysis
 *   Page 7: /patients/:patient_id/visits/:visit_id/summary -> VisitSummary
 *
 * Additional Views:
 *   /patients/:patient_id/medications -> PatientMedicationHistory
 *   /patients/:patient_id/history-assistant -> PatientHistoryAssistant
 *   /dashboard -> PatientDashboard
 *   /review/console or /review/safety -> Console (24-Rule Engine / Guidelines Explorer)
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
          <Route path="/patient-type" component={PatientTypeSelection} />
          <Route path="/clinical-tools" component={ClinicalToolsLanding} />
          <Route path="/clinical-tools/guidelines" component={GuidelinesPage} />
          <Route path="/clinical-tools/evidence" component={EvidencePage} />
          <Route path="/clinical-tools/safety" component={SafetyEnginePage} />
          <Route path="/clinical-tools/reference" component={ReferencePage} />
          <Route path="/patients/returning" component={SelectReturningPatient} />
          <Route path="/patients/new" component={RegisterNewPatient} />
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
    <Router hook={useHashLocation}>
      <Shell />
    </Router>
  );
}
