let p=null,h=null,I=[],_=null,$="mock_attending_token";function n(e){return e==null?"":String(e).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;")}const u=e=>document.getElementById(e);function M(){N(),R(),O(),V();const e=u("clinicianRoleSelect");S(e?e.value:"ATTENDING_PHYSICIAN"),x(),G(),T(),C(),J(),W(),Q(),H()}document.addEventListener("DOMContentLoaded",()=>{M()});window.addEventListener("antibiotix:sync-patient",e=>{const a=e?.detail?.patient_id||sessionStorage.getItem("antibiotix:selectedPatient");if(a&&(!p||p.patient_id!==a)?x(a):p||x(),C(),(e?.detail?.view||document.querySelector("[data-antibiotix-console]")?.getAttribute("data-review-intent"))==="safety"){const i=u("analyzeDirectBtn")||u("extractBtn");i&&(i.classList.add("pulse-focus"),setTimeout(()=>i.classList.remove("pulse-focus"),2500))}});async function S(e){try{const a=await fetch("/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username:"CLINICIAN-DEMO",role:e})});a.ok&&($=(await a.json()).access_token)}catch(a){console.warn("Could not authenticate role:",a)}}function N(){document.querySelectorAll(".nav-tab").forEach(e=>{e.addEventListener("click",()=>{document.querySelectorAll(".nav-tab").forEach(i=>i.classList.remove("active")),document.querySelectorAll(".tab-pane").forEach(i=>i.classList.remove("active")),e.classList.add("active");const a=e.getAttribute("data-tab"),t=document.getElementById(a);t&&t.classList.add("active"),a==="tab-audit"&&(T(),h&&P(h))})})}function R(){themeToggleBtn&&themeToggleBtn.addEventListener("click",()=>{const e=document.documentElement,t=e.getAttribute("data-theme")==="dark"?"light":"dark";e.setAttribute("data-theme",t),themeIcon&&(themeIcon.textContent=t==="dark"?"◐":"◑")})}let E=[],L=!1;async function x(e){try{E=await(await fetch("/api/patients")).json();const t=u("patientSelect");if(!t)return;const i=e||p&&p.patient_id||sessionStorage.getItem("antibiotix:selectedPatient")||t.value;t.innerHTML="",E.forEach(s=>{const d=document.createElement("option");d.value=s.patient_id,d.textContent=`${s.patient_id} • Age ${s.age||"Unk"} (${s.age_category}) • ${s.sex||"Unk"}`,t.appendChild(d)}),L||(t.addEventListener("change",s=>{const d=E.find(r=>r.patient_id===s.target.value);d&&(D(),w(d))}),L=!0);const o=E.find(s=>s.patient_id===i)||E[0];o&&(t.value=o.patient_id,w(o)),C()}catch{y("Failed to load patient records","danger")}}function A(){h=null,_=null;const e=document.getElementById("statsBanner");e&&e.classList.add("hidden"),["statCrit","statHigh","statMod"].forEach(r=>{const l=document.getElementById(r);l&&(l.textContent="0")});const a=document.getElementById("statSteward");a&&(a.textContent="--");const t=document.getElementById("statusBadgeContainer");t&&(t.innerHTML='<span class="badge badge-idle">Awaiting Analysis</span>');const i=document.getElementById("llmExplanationText");i&&(i.textContent="");const o=document.getElementById("injectionBanner");o&&o.classList.add("hidden");const s=document.getElementById("warningsCount");s&&(s.textContent="0");const d=document.getElementById("warningsList");d&&(d.innerHTML=`
      <div class="empty-state">
        <span class="empty-icon" aria-hidden="true">□</span>
        <p>No prescription analyzed yet. Select a patient and enter a prescription on the left to run safety checks.</p>
      </div>`),["guidelineCard","amrCard"].forEach(r=>{const l=document.getElementById(r);l&&l.classList.add("hidden")})}function D(){A(),k(),I=[];const e=document.getElementById("diagnosisInput"),a=document.getElementById("freeTextInput");e&&(e.value=""),a&&(a.value="");const t=document.getElementById("extractionCard");t&&t.classList.add("hidden")}function H(){["diagnosisInput","freeTextInput"].forEach(e=>{const a=document.getElementById(e);a&&a.addEventListener("input",()=>{if(h||document.querySelector(".warning-card")){A();const t=document.getElementById("extractionCard");t&&t.classList.add("hidden")}})})}function w(e){p=e,e&&e.patient_id&&sessionStorage.setItem("antibiotix:selectedPatient",e.patient_id),document.getElementById("patId").textContent=e.patient_id||"--",document.getElementById("patAgeSex").textContent=`${e.age??"Unknown"} yrs (${e.age_category||"N/A"}) • ${e.sex||"Unknown"}`,document.getElementById("patWeight").textContent=e.weight_kg?`${e.weight_kg} kg`:"Unrecorded";const a=document.getElementById("patNotes");a&&(a.textContent=e.clinical_notes||"None recorded");const t=document.getElementById("patAllergies");!e.allergy_status_known||!e.allergies||e.allergies.length===0?t.innerHTML=`<span class="badge ${e.allergy_status_known?"badge-mono":"badge-danger"}">${e.allergy_status_known?"No documented allergies (NKDA)":"Allergy Status Unknown"}</span>`:t.innerHTML=e.allergies.map(r=>`<span class="tag tag-allergy">${n(r)}</span>`).join(" ");const i=document.getElementById("patEgfr");if(e.egfr_ml_min!==null&&e.egfr_ml_min!==void 0){const r=e.egfr_ml_min<60;i.innerHTML=`<span class="val-mono ${r?"text-danger":""}">${e.egfr_ml_min} mL/min</span> <span style="font-size:0.75rem; color:var(--text-subtle);">(CKD-EPI 2021 non-race)</span>`}else i.innerHTML='<span class="val-mono text-warning">Unrecorded</span>';const o=document.getElementById("patHepatic");if(e.child_pugh_class){const r=String(e.child_pugh_class),l=/child-?pugh/i.test(r)?r:`Child-Pugh ${r}`;o.innerHTML=`<span class="badge badge-warning">${n(l)}</span>`}else o.innerHTML='<span class="val-mono">Normal / Unrecorded</span>';const s=document.getElementById("patPregnancy");e.pregnancy_status&&e.pregnancy_status!=="NOT_APPLICABLE"&&e.pregnancy_status!=="UNKNOWN"?s.innerHTML=`<span class="badge badge-danger">${n(e.pregnancy_status)}</span>`:s.innerHTML=`<span class="val-mono">${n(e.pregnancy_status||"N/A")}</span>`;const d=document.getElementById("patActiveMeds");e.active_medications&&e.active_medications.length>0?d.innerHTML=e.active_medications.map(r=>`<span class="tag">${n(r)}</span>`).join(" "):d.innerHTML='<span class="val-mono" style="font-size: 0.8rem;">None recorded</span>'}function O(){const e=u("clinicianRoleSelect");e&&!e.dataset.bound&&(e.addEventListener("change",s=>S(s.target.value)),e.dataset.bound="true");const a=u("extractBtn");a&&!a.dataset.bound&&(a.addEventListener("click",async()=>{A();const s=u("freeTextInput"),d=s?s.value.trim():"";if(!d){y("Please enter a prescription text to extract","warning");return}a.disabled=!0,a.textContent="Parsing...";try{const l=await(await fetch("/api/prescriptions/extract",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({raw_text:d})})).json();I=l.items;const g=u("diagnosisInput");l.diagnosis&&g&&!g.value&&(g.value=l.diagnosis),z(l)}catch(r){y("Extraction failed: "+r.message,"danger")}finally{a.disabled=!1,a.textContent="⌕ Parse & Extract Entities"}}),a.dataset.bound="true");const t=u("confirmExtractionBtn");t&&!t.dataset.bound&&(t.addEventListener("click",()=>j(I)),t.dataset.bound="true");const i=u("cancelExtractionBtn");i&&!i.dataset.bound&&(i.addEventListener("click",()=>u("extractionCard")?.classList.add("hidden")),i.dataset.bound="true");const o=u("analyzeDirectBtn");o&&!o.dataset.bound&&(o.addEventListener("click",()=>{const s=u("freeTextInput");if(!(s?s.value.trim():"")){y("Please enter prescription details","warning");return}u("extractBtn")?.click()}),o.dataset.bound="true")}function z(e){const a=u("extractionCard");a&&a.classList.remove("hidden");const t=u("extractionConfBadge"),i=Math.round(e.overall_confidence*100);t&&(t.textContent=`Confidence: ${i}%`,t.className=`badge ${i>=80?"badge-success":"badge-warning"}`);const o=u("extractedItemsList"),s=u("confirmExtractionBtn");if(o){if(o.innerHTML="",e.items.length===0){o.innerHTML='<p class="sub-text text-danger">No structured antimicrobial items recognized. Please enter items manually or rephrase.</p>',s&&(s.disabled=!0);return}if(s&&(s.disabled=!1),e.items.forEach((d,r)=>{const l=document.createElement("div");l.className="extracted-item-row",l.style.cssText="display:flex; justify-content:space-between; align-items:center; padding:0.6rem; margin-bottom:0.4rem; background:var(--bg-tertiary); border-radius:var(--radius-sm); border:1px solid var(--border-subtle);",l.innerHTML=`
      <div>
        <strong style="color:var(--accent-secondary);">${n(d.medication_name)}</strong>
        <span style="margin-left:0.5rem; font-size:0.85rem; color:var(--text-muted);">
          ${d.dose?n(d.dose+" "+(d.unit||"mg")):'<span class="text-warning">Missing Dose</span>'} • 
          ${d.route?n(d.route):'<span class="text-warning">Missing Route</span>'} • 
          ${d.frequency?n(d.frequency):'<span class="text-warning">Missing Freq</span>'} • 
          ${d.duration_days?n(d.duration_days+" days"):'<span class="text-warning">Missing Duration</span>'}
        </span>
      </div>
      <div>
        <span class="badge badge-subtle">${n(d.aware_category||"ACCESS")}</span>
      </div>
    `,o.appendChild(l)}),e.needs_clinician_confirmation){const d=document.createElement("div");d.style.cssText="margin-top:0.6rem; padding:0.5rem; background:rgba(245, 158, 11, 0.15); border:1px solid rgba(245, 158, 11, 0.3); border-radius:var(--radius-sm); font-size:0.8rem; color:#fcd34d;",d.innerHTML="<strong>Clinician Confirmation Required:</strong> Extracted prescription contains ambiguous or missing dosing/duration fields. Please review carefully before executing safety rules.",o.appendChild(d)}}}async function j(e){if(!p){y("No patient selected","warning");return}const a=u("analysisLoading"),t=u("analysisResults"),i=u("warningsList");a&&a.classList.remove("hidden"),t&&t.classList.remove("hidden"),i&&(i.innerHTML="");try{const o=u("clinicianRoleSelect"),s=u("diagnosisInput"),d=u("freeTextInput"),r={patient_id:p.patient_id,diagnosis:s&&s.value.trim()||"Unspecified Indication",raw_text:d?d.value.trim():"",items:e,clinician_id:"DOC-DEMO-01",clinician_role:o?o.value:"ATTENDING_PHYSICIAN"};h=(await(await fetch("/api/prescriptions",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(r)})).json()).prescription_id;const m=await(await fetch(`/api/prescriptions/${h}/analyze`,{method:"POST"})).json();U(m),y("Prescription safety analysis complete.","success")}catch(o){y("Analysis error: "+o.message,"danger")}finally{a&&a.classList.add("hidden")}}function U(e){statsBanner.classList.remove("hidden"),statCrit.textContent=e.critical_warnings_count??0,statHigh.textContent=e.high_warnings_count??0,statMod.textContent=e.moderate_warnings_count??0;const a=e.stewardship_summary?.stewardship_priority||{tier:"LOW"};statSteward.textContent=a.tier||"LOW",statSteward.className=`stat-number ${a.tier==="HIGH"?"text-danger":a.tier==="MODERATE"?"text-warning":"text-success"}`;const t=Array.isArray(e.warnings)?e.warnings:[],i=t.some(c=>c.rule_id==="COVERAGE-001"),o=document.getElementById("statusBadgeContainer");(e.critical_warnings_count||0)>0?o.innerHTML='<span class="badge" style="background: var(--critical-bg); border: 1px solid var(--critical-border); color: var(--critical-text);">Critical Concerns Identified</span>':i?o.innerHTML='<span class="badge" style="background: var(--high-bg); border: 1px solid var(--high-border); color: var(--high-text);">Safety Unassessed (Uncovered Drug)</span>':(e.high_warnings_count||0)>0||(e.moderate_warnings_count||0)>0?o.innerHTML=`<span class="badge" style="background: var(--high-bg); border: 1px solid var(--high-border); color: var(--high-text);">Review Recommended (${e.total_warnings||t.length})</span>`:o.innerHTML='<span class="badge" style="background: var(--success-bg); border: 1px solid var(--success-border); color: var(--success-text);">No Safety Concerns Triggered</span>',llmExplanationCard.classList.remove("hidden");const s=document.getElementById("injectionBanner");if(s){const c=!!(e.model_version_info&&e.model_version_info.injection_detected);s.classList.toggle("hidden",!c)}llmExplanationText.textContent=e.explanation||"";const d=e.model_version_info||{},r=(d.evidence_hash||"").substring(0,16);llmModelBadge.textContent=`${d.explainer_component||"Deterministic Explainer"} • SHA: ${r?`${r}...`:"N/A"}`,q(e),warningsCount.textContent=e.total_warnings??t.length,warningsList.innerHTML="",t.length===0?warningsList.innerHTML=`
      <div class="alert alert-success" style="background: var(--success-bg); border: 1px solid var(--success-border); color: var(--success-text); padding: 1rem; border-radius: var(--radius-md);">
        <strong>✓ Clinical Safety Evaluation:</strong> No drug-allergy, renal, hepatic, teratogenicity, or drug-drug interaction concerns were detected for this prescription order against ICMR National Guidelines.
      </div>
    `:t.forEach(c=>{const m=document.createElement("div"),f=(c.severity||"info").toLowerCase();m.className=`warning-card ${f} ${c.status==="OVERRIDDEN"?"overridden":""}`,m.id=`card-${c.warning_id}`,m.innerHTML=`
        <div class="warning-header">
          <div>
            <span class="warning-title">${n(c.title||"Safety Warning")}</span>
            <div class="evidence-meta" style="margin-top: 0.25rem;">
              <span>Rule ID: <strong>${n(c.rule_id||"")}</strong></span> • 
              <span>Approved by: <em>${n(c.rule_author||"Clinical Committee")}</em></span>
            </div>
          </div>
          <div class="warning-badges">
            <span class="badge" style="background: var(--${f}-bg); border: 1px solid var(--${f}-border); color: var(--${f}-text);">${n(c.severity||"")}</span>
            <span class="badge badge-subtle">${n(c.category||"")}</span>
          </div>
        </div>

        <div class="warning-body">
          <p class="concern-text">${n(c.clinical_concern||"")}</p>
          <div class="recommendation-box">
            <strong>Recommended Clinical Action:</strong> ${n(c.recommendation||"")}
          </div>
          ${c.interacting_factor?`<p class="sub-text" style="font-size: 0.8rem; color: var(--text-subtle);">Interacting Factor: ${n(c.interacting_factor)}</p>`:""}
        </div>

        <div class="warning-footer">
          <div class="evidence-meta">
            <span>≣ ${n(c.evidence?.document_title||"Authorised Source")} (${n(c.evidence?.guideline_version||"")})</span>
          </div>
          <div class="warning-actions">
            <button class="btn btn-secondary btn-sm" onclick="viewWarningEvidence('${n(c.warning_id)}')">
              View Evidence
            </button>
            ${c.status==="ACTIVE"?`
              <button class="btn btn-danger btn-sm" id="btn-override-${n(c.warning_id)}">
                Clinician Override
              </button>
            `:`
              <span class="badge badge-mono">OVERRIDDEN</span>
            `}
          </div>
        </div>
      `,warningsList.appendChild(m);const v=m.querySelector(`#btn-override-${CSS.escape(c.warning_id)}`);v&&v.addEventListener("click",()=>{F(c.warning_id,c.title,c.clinical_concern)})});const l=Array.isArray(e.guideline_recommendations)?e.guideline_recommendations:[];if(l.length>0){guidelineCard.classList.remove("hidden");const c=l[0];guidelineContent.innerHTML=`
      <div style="margin-bottom: 0.5rem;"><strong>Syndrome:</strong> ${n(c.syndrome_name||"")}</div>
      <div style="margin-bottom: 0.5rem;"><strong>Preferred First-Line:</strong> <span class="tag" style="background: rgba(16, 185, 129, 0.15); color: #34d399;">${c.first_line_preferred?n(c.first_line_preferred.join(", ")):"--"}</span></div>
      ${c.recommended_duration_days?`<div style="margin-bottom: 0.5rem;"><strong>Recommended Duration:</strong> ${n(c.recommended_duration_days)}</div>`:""}
      <p class="clinical-note-text" style="margin-top: 0.5rem;">${n(c.clinical_notes||"")}</p>
    `}else guidelineCard.classList.add("hidden");const g=Array.isArray(e.local_amr_context)?e.local_amr_context:[];if(g.length>0){amrCard.classList.remove("hidden");let c=`
      <table class="data-table">
        <thead>
          <tr>
            <th>Organism</th>
            <th>Antimicrobial</th>
            <th>Resistance Rate</th>
            <th>Sample Size</th>
            <th>Clinical Implication</th>
          </tr>
        </thead>
        <tbody>
    `;g.forEach(m=>{c+=`
        <tr>
          <td><strong>${n(m.organism||"")}</strong></td>
          <td>${n(m.antimicrobial||"")}</td>
          <td><span class="badge ${m.resistance_rate_pct>50?"badge-danger":"badge-warning"}">${m.resistance_rate_pct}%</span></td>
          <td>${m.sample_size?m.sample_size.toLocaleString():"--"}</td>
          <td style="font-size: 0.8rem;">${n(m.clinical_implication||"")}</td>
        </tr>
      `}),c+="</tbody></table>",amrContent.innerHTML=c}else amrCard.classList.add("hidden")}function q(e){const a=document.getElementById("clinicalReport");if(!a)return;const t=e.patient_summary||{},o=(Array.isArray(e.items)?e.items:[]).map(c=>`${n(c.medication_name||"")} ${c.dose?n(c.dose+" "+(c.unit||"")):"dose not recorded"} · ${n(c.route||"route not recorded")} · ${n(c.frequency||"frequency not recorded")} · ${c.duration_days?n(c.duration_days+" days"):"duration not recorded"}`).join("<br>")||"No structured medication recorded",d=(Array.isArray(e.retrieved_guideline_evidence)?e.retrieved_guideline_evidence:Array.isArray(e.retrieved_guideline_evidence?.retrieved)?e.retrieved_guideline_evidence.retrieved:[]).map(c=>`<li><strong>${n(c.document_title||"Authorised source")}</strong> · ${n(c.guideline_version||"")}${c.section_page?` · ${n(c.section_page)}`:""}<br><q>${n(c.verbatim_passage||"")}</q></li>`).join("")||"<li>No retrieved guideline passage recorded.</li>",r=Array.isArray(e.warnings)?e.warnings:[],l=r.map(c=>`<tr><td><span class="report-severity">${n(c.severity||"")}</span></td><td>${n(c.title||"")}</td><td>${n(c.clinical_concern||"")}</td><td>${n(c.recommendation||"")}</td></tr>`).join("")||'<tr><td colspan="4">No safety concerns identified by the deterministic engine.</td></tr>',g=e.stewardship_summary?.stewardship_priority||{};a.innerHTML=`
    <div class="report-header"><div><span class="report-label">ANTIBIOTIX</span><h5>Clinical Decision Support Summary Report</h5></div><dl><dt>Report date</dt><dd>${n(new Date().toLocaleString())}</dd><dt>Report ID</dt><dd>${n(e.prescription_id||"")}</dd><dt>Reviewing role</dt><dd>Authorized clinician</dd></dl></div>
    <div class="report-grid">
      <section><h6>1. Patient Summary</h6><p><b>Patient:</b> ${n(e.patient_id||"")} · <b>Demographics:</b> ${n(t.age??"Unknown")} yrs · ${n(t.sex||"Unknown")}</p><p><b>Allergies:</b> ${n((t.allergies||[]).join(", ")||"None documented")}<br><b>Current medications:</b> ${n((t.active_medications||[]).join(", ")||"None recorded")}<br><b>Renal:</b> ${n(t.egfr_ml_min??"Not recorded")} mL/min · <b>Hepatic:</b> ${n(t.child_pugh_class||"Not recorded")} · <b>Pregnancy:</b> ${n(t.pregnancy_status||"Unknown")}</p></section>
      <section><h6>2. Visit Information</h6><p><b>Visit date:</b> ${n(new Date().toLocaleString())}<br><b>Diagnosis / indication:</b> ${n(e.diagnosis||"Not recorded")}</p></section>
      <section><h6>3. Medication or Prescription Under Review</h6><p>${o}</p></section>
      <section><h6>4. Evidence Reviewed</h6><ul>${d}</ul></section>
    </div>
    <section class="report-findings"><h6>5. Clinical Decision Support Findings</h6><p><b>Stewardship classification:</b> ${n(g.tier||"Not recorded")} · <b>Warnings:</b> ${n(e.total_warnings??r.length)}</p><div class="table-responsive"><table class="data-table"><thead><tr><th>Severity</th><th>Concern</th><th>Clinical detail</th><th>System recommendation</th></tr></thead><tbody>${l}</tbody></table></div></section>
    <div class="report-grid"><section><h6>6. Clinical Recommendation</h6><p>System advice is represented by the findings and recommendations above. The final decision remains the clinician's judgment.</p></section><section><h6>7. Clinician Decision</h6><p>Status: Pending clinician decision<br>Clinician rationale: To be documented in the clinical record.</p></section><section><h6>8. Governance and Audit Information</h6><p>Review status: ${n(e.total_warnings||r.length?"Safety review required":"No findings recorded")}<br>Immutable prescription metadata: ${n(e.model_version_info?.engine_build||"Versioned engine metadata attached")}</p></section></div>`}window.viewWarningEvidence=async function(e){try{const t=await(await fetch(`/api/warnings/${e}/evidence`)).json();evidenceModalBody.innerHTML=`
      <div style="margin-bottom: 1rem;">
        <span class="badge badge-mono">Rule ID: ${n(t.rule_id)}</span>
        <h4 style="margin-top: 0.5rem;">Supporting Clinical Evidence for ${n(t.prescribed_drug)}</h4>
      </div>

      <div class="patient-summary-box" style="margin-bottom: 1rem;">
        <div style="margin-bottom: 0.4rem;"><strong>Guideline Document:</strong> ${n(t.document_title)}</div>
        <div style="margin-bottom: 0.4rem;"><strong>Guideline Version:</strong> ${n(t.guideline_version)}</div>
        <div style="margin-bottom: 0.4rem;"><strong>Author / Committee:</strong> ${n(t.rule_author)}</div>
        <div><strong>Approval Status:</strong> <span class="badge badge-icmr">${n(t.rule_approval_status)}</span></div>
        ${t.source_url?`<div style="margin-top: 0.4rem;"><strong>Source URL:</strong> <a href="${n(t.source_url)}" target="_blank" style="color:var(--accent-primary); word-break:break-all;">${n(t.source_url)}</a></div>`:""}
      </div>

      <div class="recommendation-box" style="margin-bottom: 1rem; border-left-color: var(--accent-primary);">
        <strong style="display: block; margin-bottom: 0.25rem;">Verbatim Guideline Citation:</strong>
        <p style="font-style: italic; font-size: 0.9rem;">"${n(t.verbatim_passage)}"</p>
      </div>

      ${t.unverified_sources&&t.unverified_sources.length?`
        <div class="recommendation-box" style="margin-bottom:1rem; border-left-color: var(--high-border);">
          <strong style="display:block; margin-bottom:0.25rem;">Cited without a source document in this system</strong>
          <p class="sub-text" style="font-size:0.8rem; margin:0;">
            This rule's clinical rationale names ${t.unverified_sources.map(n).join(", ")}.
            ${t.unverified_sources.length===1?"That authority is":"Those authorities are"}
            not held in this repository, so the passage above cannot be retrieved from
            ${t.unverified_sources.length===1?"it":"them"}. Treat as unverified.
          </p>
        </div>
      `:""}

      ${t.supporting_labels&&t.supporting_labels.length?`
        <div style="margin-bottom: 1rem;">
          <strong style="display:block; margin-bottom:0.4rem; font-size:0.8rem; text-transform:uppercase; color:var(--text-subtle);">
            Supporting Regulatory Product Labelling
          </strong>
          <p class="sub-text" style="font-size:0.75rem; margin-bottom:0.5rem;">
            Distinct evidence class from the guideline citation above. US FDA product labelling &mdash;
            not ICMR or WHO guidance. Indian CDSCO labelling may differ.
          </p>
          ${t.supporting_labels.map(i=>`
            <div class="patient-summary-box" style="margin-bottom:0.6rem;">
              <div style="margin-bottom:0.3rem;"><strong>Label:</strong> ${n(i.document_title||"")}</div>
              <div style="margin-bottom:0.3rem;"><strong>Issuer:</strong> ${n(i.issuing_org||"")}</div>
              <div style="margin-bottom:0.3rem;"><strong>Scope:</strong> ${n(i.geographic_scope||"")}</div>
              <div style="margin-bottom:0.3rem;"><strong>Version:</strong> ${n(i.guideline_version||"")}${i.publication_date?" &middot; "+n(i.publication_date):""}</div>
              ${i.section_page?`<div style="margin-bottom:0.3rem;"><strong>Section:</strong> ${n(i.section_page)}</div>`:""}
              <p style="font-style:italic; font-size:0.85rem; margin-top:0.4rem;">"${n(i.verbatim_passage||"")}"</p>
              ${i.source_url?`<a href="${n(i.source_url)}" target="_blank" style="color:var(--accent-primary); font-size:0.75rem; word-break:break-all;">${n(i.source_url)}</a>`:""}
            </div>
          `).join("")}
        </div>
      `:""}

      <div class="precedence-banner" style="padding: 0.75rem; background: var(--bg-tertiary); border-radius: var(--radius-md);">
        <strong style="font-size: 0.8rem; text-transform: uppercase; color: var(--text-subtle);">Guideline Precedence Policy:</strong>
        <p style="font-size: 0.85rem; margin-top: 0.25rem;">National ICMR Guideline (Rank 2) takes precedence in Indian clinical setting over generic international guidelines.</p>
      </div>
    `,evidenceModal.classList.remove("hidden")}catch(a){y("Error retrieving evidence: "+a.message,"danger")}};function V(){const e=u("closeEvidenceModal");e&&!e.dataset.bound&&(e.addEventListener("click",()=>u("evidenceModal")?.classList.add("hidden")),e.dataset.bound="true");const a=u("closeEvidenceBtn");a&&!a.dataset.bound&&(a.addEventListener("click",()=>u("evidenceModal")?.classList.add("hidden")),a.dataset.bound="true");const t=u("closeOverrideModal");t&&!t.dataset.bound&&(t.addEventListener("click",()=>u("overrideModal")?.classList.add("hidden")),t.dataset.bound="true");const i=u("cancelOverrideBtn");i&&!i.dataset.bound&&(i.addEventListener("click",()=>u("overrideModal")?.classList.add("hidden")),i.dataset.bound="true");const o=u("submitOverrideBtn");o&&!o.dataset.bound&&(o.addEventListener("click",async()=>{const s=u("overrideReasonInput"),d=s?s.value.trim():"";if(d.length<10){y("Please provide a substantive clinical rationale for the override (min 10 characters).","warning");return}const r=u("clinicianRoleSelect"),l={warning_id:_,override_reason:d};try{const g=await fetch(`/api/warnings/${_}/override`,{method:"POST",headers:{"Content-Type":"application/json",Authorization:`Bearer ${$}`},body:JSON.stringify(l)});if(!g.ok){const v=await g.json();throw new Error(v.detail||"Override unauthorized")}const c=await g.json();u("overrideModal")?.classList.add("hidden"),y("Warning successfully overridden and logged in immutable audit trail.","success");const m=document.querySelector(`[data-warning-id="${_}"]`);m&&(m.outerHTML=`<span class="badge badge-success" style="font-size:0.75rem;">Overridden by ${n(c.clinician_role||r?.value)}</span>`);const f=document.getElementById(`warn-card-${_}`);if(f){const v=document.createElement("div");v.style.cssText="margin-top:0.6rem; padding:0.5rem; background:rgba(34, 197, 94, 0.1); border-left:3px solid var(--accent-success); border-radius:var(--radius-sm); font-size:0.8rem;",v.innerHTML=`<strong>Documented Rationale:</strong> ${n(d)}`,f.appendChild(v)}T(),h&&P(h)}catch(g){y("Override failed: "+g.message,"danger")}}),o.dataset.bound="true")}function F(e,a,t){_=e;const i=u("clinicianRoleSelect"),o=i?i.value:"ATTENDING_PHYSICIAN",s=u("overrideClinicianRole");s&&(s.value=o);const d=u("overrideReasonInput");d&&(d.value="");const r=u("overrideWarningSummary");r&&(r.innerHTML=`
      <div style="font-weight: 700; color: var(--text-main); margin-bottom: 0.25rem;">${n(a)}</div>
      <div style="font-size: 0.85rem; color: var(--text-muted);">${n(t)}</div>
    `),u("overrideModal")?.classList.remove("hidden")}async function G(){try{const a=await(await fetch("/api/guidelines/rules")).json(),t=document.getElementById("totalRulesCount");t&&(t.textContent=a.total_rules);const i=document.getElementById("rulesTableBody");if(!i)return;i.innerHTML="",a.rules.forEach(s=>{const d=document.createElement("tr");d.innerHTML=`
        <td><span class="val-mono" style="font-weight: 700;">${n(s.rule_id)}</span></td>
        <td><span class="badge badge-subtle">${n(s.category)}</span></td>
        <td><span class="badge" style="background: var(--${s.severity.toLowerCase()}-bg); color: var(--${s.severity.toLowerCase()}-text);">${n(s.severity)}</span></td>
        <td><strong>${n(s.rule_name)}</strong><br><span style="font-size: 0.8rem; color: var(--text-muted);">${n(s.description)}</span></td>
        <td>${n(s.evidence_source)}<br><span class="val-mono" style="font-size: 0.75rem;">${n(s.guideline_version)}</span></td>
        <td>${n(s.author)}<br><span class="badge badge-icmr" style="font-size: 0.7rem;">${n(s.approval_status)}</span></td>
      `,i.appendChild(d)});const o=document.getElementById("ruleSearchInput");o&&o.addEventListener("input",s=>{const d=s.target.value.toLowerCase();document.querySelectorAll("#rulesTableBody tr").forEach(r=>{const l=r.textContent.toLowerCase();r.style.display=l.includes(d)?"":"none"})})}catch(e){console.error("Error loading rules catalog:",e)}}async function T(){try{const a=await(await fetch("/api/audit/alert-fatigue")).json(),t=document.getElementById("fatigueTableBody");if(!t)return;t.innerHTML="",a.forEach(i=>{const o=document.createElement("tr");o.innerHTML=`
        <td><span class="val-mono" style="font-weight: 700;">${n(i.rule_id)}</span></td>
        <td>${i.total_triggered}</td>
        <td>${i.total_overridden}</td>
        <td><strong>${i.override_rate_pct}%</strong></td>
        <td>
          ${i.requires_clinical_recalibration?`
            <span class="badge badge-danger">FLAGGED (>60% Overridden)</span>
          `:`
            <span class="badge badge-success">Calibrated</span>
          `}
        </td>
        <td style="font-size: 0.8rem; color: var(--text-muted);">${n(i.recommendation)}</td>
      `,t.appendChild(o)})}catch(e){console.error("Error loading alert fatigue metrics:",e)}}function k(){const e=document.getElementById("auditStream");e&&(e.innerHTML=`
      <div class="empty-state">
        <p>No prescription analysed in this session yet. Run an analysis to view its
        cryptographically chained audit trail.</p>
      </div>`);const a=document.getElementById("auditContext");a&&(a.textContent="")}async function P(e){if(!e){k();return}try{const t=await(await fetch(`/api/audit/logs?limit=20&prescription_id=${e}`)).json(),i=document.getElementById("auditStream");if(!i)return;i.innerHTML="";const o=document.getElementById("auditContext");if(o&&(o.textContent=`Showing prescription ${e}`+(p?` for ${p.patient_id}`:"")),!t.length){i.innerHTML='<div class="empty-state"><p>No audit records yet for this prescription.</p></div>';return}t.forEach(s=>{const d=document.createElement("div");d.className="audit-entry",d.innerHTML=`
        <div class="evidence-meta">
          <span class="badge badge-subtle">${n(s.event_type)}</span>
          <span class="val-mono" style="font-size:0.75rem;">${n(s.log_id)}</span>
          <span style="font-size:0.8rem;">${n(new Date(s.timestamp).toLocaleString())}</span>
        </div>
        <p style="font-size:0.85rem; margin:0.35rem 0;">${n(s.action_summary)}</p>
        <div class="evidence-meta" style="font-size:0.75rem;">
          <span>Clinician: <strong>${n(s.clinician_id)}</strong> (${n(s.clinician_role)})</span>
        </div>
        <div class="evidence-meta" style="font-size:0.7rem;">
          <span>prev: <span class="val-mono">${n(String(s.prev_hash||"GENESIS").substring(0,16))}…</span></span>
          <span>hash: <span class="val-mono" title="${n(s.integrity_hash)}">${n(s.integrity_hash.substring(0,16))}…</span></span>
        </div>
      `,i.appendChild(d)})}catch(a){console.error("Error loading audit logs:",a)}}async function C(){let a=[{key:"cap-amox-pen-allergy",label:"CAP: Amox in Penicillin Allergy",patient_id:"PATIENT-001",diagnosis:"Community-Acquired Pneumonia (CAP)",text:"Amoxicillin 500mg PO TID x 7 days for community acquired pneumonia",source:"seed"},{key:"uti-nitro-ckd",label:"UTI: Nitrofurantoin in CKD-4",patient_id:"PATIENT-002",diagnosis:"Uncomplicated Urinary Tract Infection (Cystitis)",text:"Nitrofurantoin 100mg PO BID x 5 days for acute cystitis",source:"seed"},{key:"cirrhosis-metronidazole",label:"Cirrhosis: Metronidazole Overdose",patient_id:"PATIENT-003",diagnosis:"Intra-abdominal Infection",text:"Metronidazole 500mg IV TID x 10 days",source:"seed"},{key:"pregnancy-ciprofloxacin",label:"Pregnancy: Ciprofloxacin",patient_id:"PATIENT-004",diagnosis:"Acute Pyelonephritis",text:"Ciprofloxacin 500mg PO BID x 7 days",source:"seed"},{key:"ddi-clarithro-warfarin",label:"DDI: Clarithromycin + Warfarin/Statin",patient_id:"PATIENT-005",diagnosis:"Acute Bacterial Bronchitis",text:"Clarithromycin 500mg PO BID x 7 days",source:"seed"},{key:"peds-cefaclor-otitis",label:"Peds Otitis: Cefaclor in Cephalosporin Allergy",patient_id:"PATIENT-006",diagnosis:"Acute Otitis Media (Pediatric)",text:"Cefaclor 250mg PO TID x 7 days for acute otitis media",source:"seed"},{key:"ddi-qt-azithro",label:"DDI: Azithro + Ondansetron (QT)",patient_id:"PATIENT-007",diagnosis:"Atypical Pneumonia",text:"Azithromycin 500mg PO QD x 5 days",source:"seed"},{key:"ddi-linezolid-ssri",label:"DDI: Linezolid + Escitalopram",patient_id:"PATIENT-008",diagnosis:"MRSA Soft Tissue Infection",text:"Linezolid 600mg PO BID x 10 days",source:"seed"},{key:"sepsis-erythromycin",label:"Sepsis: Erythromycin in Macrolide Allergy",patient_id:"PATIENT-009",diagnosis:"Suspected Sepsis",text:"Erythromycin 500mg IV Q6H x 7 days",source:"seed"},{key:"sinusitis-doxy-pregnancy",label:"Sinusitis: Doxycycline in Unconfirmed Pregnancy",patient_id:"PATIENT-010",diagnosis:"Acute Bacterial Sinusitis",text:"Doxycycline 100mg PO BID x 7 days",source:"seed"},{key:"cellulitis-vancomycin",label:"Cellulitis: Vancomycin in Glycopeptide Allergy",patient_id:"PATIENT-011",diagnosis:"Non-purulent Cellulitis",text:"Vancomycin 1g IV Q12H x 7 days",source:"seed"},{key:"pyelo-ceftriaxone",label:"Pyelonephritis: Ceftriaxone in Beta-Lactam Allergy",patient_id:"PATIENT-012",diagnosis:"Acute Pyelonephritis",text:"Ceftriaxone 2g IV QD x 7 days",source:"seed"},{key:"hap-doxycycline",label:"HAP: Doxycycline in Tetracycline Allergy",patient_id:"PATIENT-013",diagnosis:"Hospital-Acquired Pneumonia",text:"Doxycycline 100mg PO BID x 7 days",source:"seed"},{key:"diarrhoea-nitrofurantoin",label:"Enteritis: Nitrofurantoin in Nitro Allergy",patient_id:"PATIENT-014",diagnosis:"Acute Infectious Diarrhoea",text:"Nitrofurantoin 100mg PO BID x 5 days",source:"seed"},{key:"meningitis-azithromycin",label:"Meningitis: Azithromycin in Macrolide Allergy",patient_id:"PATIENT-015",diagnosis:"Suspected Bacterial Meningitis",text:"Azithromycin 500mg IV QD x 10 days",source:"seed"},{key:"endocarditis-gentamicin",label:"Endocarditis: Gentamicin in Aminoglycoside Allergy",patient_id:"PATIENT-016",diagnosis:"Prosthetic-Valve Endocarditis",text:"Gentamicin 70mg IV Q8H x 14 days",source:"seed"},{key:"peds-pharyngitis-clinda",label:"Peds Pharyngitis: Clindamycin in Lincosamide Allergy",patient_id:"PATIENT-017",diagnosis:"Group-A Streptococcal Pharyngitis",text:"Clindamycin 300mg PO TID x 10 days",source:"seed"},{key:"dental-colistin",label:"Dental: Colistin in Polymyxin Allergy",patient_id:"PATIENT-018",diagnosis:"Acute Odontogenic Infection",text:"Colistin 150mg IV BID x 5 days",source:"seed"},{key:"copd-levofloxacin",label:"COPD Exacerbation: Levofloxacin in Quinolone Allergy",patient_id:"PATIENT-019",diagnosis:"Bacterial COPD Exacerbation",text:"Levofloxacin 500mg PO QD x 5 days",source:"seed"},{key:"enteric-cefixime",label:"Enteric Fever: Cefixime in Cephalosporin Allergy",patient_id:"PATIENT-020",diagnosis:"Uncomplicated Enteric Fever",text:"Cefixime 200mg PO BID x 10 days",source:"seed"}];try{const i=await fetch("/api/scenario-presets");if(i.ok){const o=await i.json();Array.isArray(o)&&o.length>0&&(a=o)}}catch{}const t=document.getElementById("scenarioPresetsContainer")||document.querySelector(".quick-presets");t&&(t.innerHTML='<span class="preset-label">Quick Scenario Presets:</span>',a.forEach(i=>{const o=document.createElement("button");o.className=`btn btn-chip ${i.source==="registered"?"registered-chip":""}`,o.setAttribute("data-preset",i.key),o.textContent=i.label||i.key,o.addEventListener("click",()=>{i.patient_id&&patientSelect&&(patientSelect.value=i.patient_id,patientSelect.dispatchEvent(new Event("change"))),diagnosisInput&&(diagnosisInput.value=i.diagnosis||""),freeTextInput&&(freeTextInput.value=i.text||""),y(`Loaded preset: ${i.label||o.textContent}`,"info")}),t.appendChild(o)}))}function W(){const e=document.getElementById("askInput"),a=document.getElementById("askBtn"),t=document.getElementById("askResults");if(!e||!a||!t)return;async function i(){const o=e.value.trim();if(o){a.disabled=!0,t.innerHTML='<p class="sub-text">Searching the ingested guideline corpus…</p>';try{const d=await(await fetch("/api/evidence/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({question:o,k:4})})).json();if(!d.answered){const r=d.injection_detected?"danger":"high";t.innerHTML=`
          <div class="recommendation-box" style="border-left-color: var(--${r}-border);">
            <strong style="display:block; margin-bottom:0.3rem;">No answer returned</strong>
            <p style="margin:0 0 0.5rem 0;">${n(d.message||"")}</p>
            <span class="badge badge-mono">${n(d.refusal_reason||"REFUSED")}</span>
          </div>`;return}t.innerHTML=`
        <div class="evidence-meta" style="margin-bottom:0.75rem;">
          <span class="badge badge-mono">${n(d.answer_mode)}</span>
          <span>${d.passage_count} passage(s) retrieved</span>
        </div>
        ${d.passages.map(r=>`
          <div class="patient-summary-box" style="margin-bottom:0.75rem;">
            <div class="evidence-meta" style="margin-bottom:0.4rem;">
              <span aria-hidden="true">≣</span> <span>${n(r.document_title||"")}</span>
              <span class="badge badge-subtle">${n(r.section_page||"")}</span>
              <span class="val-mono" style="font-size:0.72rem;">score ${r.retrieval_score}</span>
            </div>
            <p style="font-style:italic; font-size:0.86rem; white-space:pre-wrap;">"${n(r.verbatim_passage||"")}"</p>
            <div class="evidence-meta" style="font-size:0.72rem;">
              <span>${n(r.issuing_org||"")}</span>
              <span>${n(r.guideline_version||"")}</span>
              ${r.source_url?`<a href="${n(r.source_url)}" target="_blank" style="color:var(--accent-primary);">source</a>`:""}
            </div>
          </div>
        `).join("")}
        <p class="sub-text" style="font-size:0.75rem;">${n(d.disclaimer||"")}</p>`}catch(s){t.innerHTML=`<p class="sub-text">Error contacting the evidence service: ${n(s.message)}</p>`}finally{a.disabled=!1}}}a.addEventListener("click",i),e.addEventListener("keydown",o=>{o.key==="Enter"&&i()}),e.addEventListener("input",()=>{t.innerHTML=""}),document.querySelectorAll("[data-ask]").forEach(o=>{o.addEventListener("click",()=>{e.value=o.getAttribute("data-ask"),i()})})}function Q(){const e=r=>document.getElementById(r),a=r=>r&&r.classList.remove("hidden"),t=r=>r&&r.classList.add("hidden"),i={};async function o(r){if(i[r])return i[r];const l=await fetch("/api/auth/patient-login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({patient_id:r})});if(!l.ok)return null;const g=await l.json();return i[r]=g.access_token,g.access_token}function s(r,l,g){r&&(r.innerHTML=`<div class="recommendation-box" style="border-left-color: var(--${l?"success":"critical"}-border); margin-top:0.6rem;">
      <p style="margin:0; font-size:0.85rem;">${n(g)}</p></div>`)}e("openRegisterPatient")?.addEventListener("click",()=>{["regAge","regWeight","regEgfr","regMeds","regNotes"].forEach(r=>{const l=e(r);l&&(l.value="")}),e("registerResult").innerHTML="",a(e("registerModal"))}),e("closeRegisterModal")?.addEventListener("click",()=>t(e("registerModal"))),e("cancelRegister")?.addEventListener("click",()=>t(e("registerModal"))),e("submitRegister")?.addEventListener("click",async()=>{const r=(e("regMeds").value||"").split(`
`).map(v=>v.trim()).filter(Boolean),l=parseFloat(e("regEgfr").value),g=parseInt(e("regAge").value,10),c=parseFloat(e("regWeight").value),m=e("regChildPugh").value,f={age:Number.isFinite(g)?g:null,sex:e("regSex").value,weight_kg:Number.isFinite(c)?c:null,egfr_ml_min:Number.isFinite(l)?l:null,renal_status_known:Number.isFinite(l),child_pugh_class:m||null,hepatic_status_known:!!m,pregnancy_status:e("regPregnancy").value,allergy_status_known:!1,active_medications:r,clinical_notes:e("regNotes").value||null};Number.isFinite(g)&&(f.age_category=g<18?"PEDIATRIC":g>=65?"GERIATRIC":"ADULT");try{const v=await fetch("/api/patients",{method:"POST",headers:{"Content-Type":"application/json",Authorization:`Bearer ${$}`},body:JSON.stringify(f)}),b=await v.json();if(!v.ok){s(e("registerResult"),!1,b.detail||"Could not register patient.");return}i[b.patient_id]=b.patient_access_token;const B=(b.unknowns||[]).length?` Recorded as unknown: ${b.unknowns.join(", ")} — these will raise missing-information warnings.`:"";s(e("registerResult"),!0,`Created ${b.patient_id}.${B}`),y(`Registered ${b.patient_id}`,"success"),await x(b.patient_id),setTimeout(()=>t(e("registerModal")),1600)}catch(v){s(e("registerResult"),!1,"Error: "+v.message)}}),e("openManageMeds")?.addEventListener("click",()=>{if(!p){y("Select a patient first","danger");return}e("medsPatientLabel").textContent=`Patient ${p.patient_id}`,e("medsList").value=(p.active_medications||[]).join(`
`),e("medsReason").value="",e("medsResult").innerHTML="",a(e("medsModal"))}),e("closeMedsModal")?.addEventListener("click",()=>t(e("medsModal"))),e("cancelMeds")?.addEventListener("click",()=>t(e("medsModal"))),e("submitMeds")?.addEventListener("click",async()=>{if(!p)return;const r=(e("medsList").value||"").split(`
`).map(l=>l.trim()).filter(Boolean);try{const l=await fetch(`/api/patients/${p.patient_id}/medications`,{method:"PUT",headers:{"Content-Type":"application/json",Authorization:`Bearer ${$}`},body:JSON.stringify({active_medications:r,reason:e("medsReason").value||null})}),g=await l.json();if(!l.ok){s(e("medsResult"),!1,g.detail||"Could not update medications.");return}s(e("medsResult"),!0,`Updated: ${g.previous_count} → ${g.current_count}. Re-analyse to refresh interaction checks.`),y("Medications updated","success"),await x(p.patient_id),setTimeout(()=>t(e("medsModal")),1500)}catch(l){s(e("medsResult"),!1,"Error: "+l.message)}});function d(r){const l=e("allergyRecords");if(l){if(!r||!r.length){l.innerHTML='<p class="sub-text">No allergies recorded.</p>';return}l.innerHTML='<strong style="font-size:0.82rem;">Recorded allergies</strong>'+r.map(g=>{const c=g.source==="CLINICIAN_VERIFIED";return`<div class="patient-summary-box" style="margin-top:0.4rem; padding:0.5rem 0.6rem;">
          <span style="font-weight:600;">${n(g.substance)}</span>
          <span class="badge badge-${c?"mono":"danger"}" style="margin-left:0.4rem; font-size:0.7rem;">
            ${c?"Clinician-verified":"Patient-reported, unverified"}</span>
          ${g.reaction?`<div class="sub-text" style="font-size:0.76rem; margin-top:0.2rem;">Reaction: ${n(g.reaction)}</div>`:""}
        </div>`}).join("")}}e("openReportAllergy")?.addEventListener("click",()=>{if(!p){y("Select a patient first","danger");return}e("allergyPatientLabel").textContent=`Patient ${p.patient_id}`,e("allergySubstance").value="",e("allergyReaction").value="",e("allergyResult").innerHTML="",d(p.allergy_records),a(e("allergyModal"))}),e("closeAllergyModal")?.addEventListener("click",()=>t(e("allergyModal"))),e("cancelAllergy")?.addEventListener("click",()=>t(e("allergyModal"))),e("submitAllergy")?.addEventListener("click",async()=>{if(!p)return;const r=(e("allergySubstance").value||"").trim();if(r.length<2){s(e("allergyResult"),!1,"Enter the medication or substance.");return}const l=e("allergyAs").value==="PATIENT";let g=$;if(l&&(g=await o(p.patient_id),!g)){s(e("allergyResult"),!1,"Could not obtain a patient session.");return}try{const c=await fetch(`/api/patients/${p.patient_id}/allergies`,{method:"POST",headers:{"Content-Type":"application/json",Authorization:`Bearer ${g}`},body:JSON.stringify({substance:r,reaction:e("allergyReaction").value||null})}),m=await c.json();if(!c.ok){s(e("allergyResult"),!1,m.detail||"Could not record the allergy.");return}s(e("allergyResult"),!0,m.note||"Recorded."),d(m.allergy_records),y(`${r} recorded (${m.source==="SELF_REPORTED"?"unverified":"verified"})`,"success"),await x(p.patient_id)}catch(c){s(e("allergyResult"),!1,"Error: "+c.message)}})}function J(){const e=document.getElementById("runAllTestsBtn");e&&e.addEventListener("click",async()=>{const a=document.getElementById("testSuiteTableBody");e.disabled=!0,e.textContent="Running suite…",a&&(a.innerHTML='<tr><td colspan="5" style="text-align:center;">Executing automated test suite — results are read from the live pytest run, not cached.</td></tr>');try{const i=await(await fetch("/api/system/run-test-suite",{method:"POST"})).json();if(!i.executed){a&&(a.innerHTML=`
            <tr>
              <td><span class="val-mono">SUITE</span></td>
              <td>Automated Clinical Safety Suite</td>
              <td>Execution</td>
              <td>${n(i.detail||"Suite could not be executed.")}</td>
              <td><span class="badge badge-danger">${n(i.status)}</span></td>
            </tr>`),y(`Test suite did not run: ${i.status}`,"danger");return}const o=i.status==="PASSED",s=await fetch("/api/audit/verify").then(d=>d.json()).catch(()=>null);a&&(a.innerHTML=`
          <tr>
            <td><span class="val-mono">SUITE-ALL</span></td>
            <td>Automated Clinical Safety &amp; Adversarial Suite</td>
            <td>Deterministic rules, extraction, injection, authorization</td>
            <td>${n(i.summary_line||"")} (${i.duration_seconds}s)</td>
            <td><span class="badge ${o?"badge-success":"badge-danger"}">${i.passed}/${i.total} ${n(i.status)}</span></td>
          </tr>
          <tr>
            <td><span class="val-mono">AUDIT-CHAIN</span></td>
            <td>Cryptographic Audit Chain Verification</td>
            <td>SHA-256 append-only integrity</td>
            <td>${s?n(`${s.total_records} records walked from genesis`):"unavailable"}</td>
            <td><span class="badge ${s&&s.valid?"badge-success":"badge-danger"}">${s?n(String(s.verification_status||(s.valid?"VALID":"BROKEN"))):"N/A"}</span></td>
          </tr>`),y(`Test suite: ${i.passed}/${i.total} passed`,o?"success":"danger")}catch(t){a&&(a.innerHTML=`<tr><td colspan="5" style="text-align:center;">Error contacting test runner: ${n(t.message)}</td></tr>`),y("Error running test suite: "+t.message,"danger")}finally{e.disabled=!1,e.textContent="▶ Run Complete Test Suite"}})}function y(e,a="info"){const t=document.createElement("div");t.className=`toast toast-${a}`,t.style.cssText=`
    position: fixed;
    bottom: 2rem;
    right: 2rem;
    padding: 0.75rem 1.25rem;
    border-radius: var(--radius-md);
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    color: var(--text-main);
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5);
    font-size: 0.85rem;
    font-weight: 500;
    z-index: 10000;
    animation: fadeIn 0.3s ease;
  `,a==="success"?(t.style.borderColor="var(--success-border)",t.style.background="var(--success-bg)",t.style.color="var(--success-text)"):a==="danger"?(t.style.borderColor="var(--critical-border)",t.style.background="var(--critical-bg)",t.style.color="var(--critical-text)"):a==="warning"&&(t.style.borderColor="var(--high-border)",t.style.background="var(--high-bg)",t.style.color="var(--high-text)"),t.textContent=e,document.body.appendChild(t),setTimeout(()=>{t.remove()},3500)}export{M as bootApp};
