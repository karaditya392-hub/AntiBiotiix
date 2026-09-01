"""
RAG corpus provenance test suite.

The corpus now holds three provenance classes, and the whole point of these tests is
that a citation drawn from one can never be mistaken for a citation from another:

  OFFICIAL_PDF                      hash-verified publication; `p. N` is a real page
  GOOGLE_DOCS_EXPORT_TRANSCRIPTION  operator-attested edition; N is a TRANSCRIPT page
  PLAIN_TEXT_TRANSCRIPTION          operator-attested edition; no page locator exists

A transcript page rendered as "p. 4" would invite a clinician to open page 4 of an
edition where the passage may sit somewhere else entirely. That is the failure these
tests exist to prevent.
"""
import io
import json
import os

import pytest

from backend.rag.store import (
    CLINICAL_DOMAINS,
    DOMAIN_ANTIMICROBIAL,
    DOMAIN_READING_CONTRACT,
    NOT_A_CLINICAL_GUIDELINE_RANK,
    PAGE_NONE,
    PAGE_OFFICIAL,
    PAGE_TRANSCRIPT,
    GuidelineVectorStore,
    vector_store,
)

RAG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "backend", "guidelines", "data", "rag",
)

OFFICIAL = {
    "ICMR-STG-2019-ED2": "74e988ffe0603263ce131d043a187302d5845fbc4ff30aa74f9190ce99ff5016",
    "WHO-AWARE-BOOK-2022": "4960ecc4fa5bab8281feda656a0da3176dafa1fd21971d87e3b2092d7dac562f",
    "ICMR-STW-VOL3-2022": "38ae15831b78518cb2372785c363a7d061a8a6f5b42592ee2a0dd43cedae6c10",
    "ICMR-STW-PTB-EPTB-2022": "95f06c22b936875baf358853e598e4425dfc667d1857fae8d64c9d3884490ad2",
}

# MoHFW / NHSRC Standard Treatment Guidelines (scripts/ingest_mohfw_stg.py).
#
# National Indian guidelines, but CONDITION-SPECIFIC and almost entirely
# non-antimicrobial. They sit at the same precedence rank as the ICMR sources, so
# the only thing stopping a dry eye or hypertension passage from being read as
# antimicrobial guidance is the scope declaration in its notes. These tests treat
# that declaration as load-bearing and check it is actually there.
MOHFW = {
    "MOHFW-STG-SNAKEBITE-2016": "5b7ea408dade69aae0c9ab8a7536cec29bafbb190586e144bc1066fd8d1e18d9",
    "MOHFW-STG-OA-KNEE-2017": "4f09392e32f0fe866b954391b26c23792a30d846cd5a586ddd3d131c66dd9ca3",
    "MOHFW-STG-NEONATAL-JAUNDICE-2016": "be5c94263bdaa67f4a0b893e8d6135ccb92d64fd1a8fe21f6c516730220f69e3",
    "MOHFW-STG-LBW-FEEDING-UNDATED": "9bb8912d7a27f5c76877002d1e081780fa11c19789a037f9367d41ee7329b824",
    "MOHFW-STG-ACUTE-SINUSITIS-UNDATED": "925bbcd1f5ddaff8a95fc777e1609811398229a75e04f19a5910025de492f5af",
    "MOHFW-STG-RSA-2017": "24032ffe321caa23d7f3434441623f0bc028c77b92f9d89d89bd6e554487cee3",
    "MOHFW-STG-PAED-RESP-INFECTIONS-2016": "5453d568e787c9f1bb5f4e8e3ad04af6e016d3d015589173b9ac13e167eb1673",
    "MOHFW-STG-DIABETIC-FOOT-2016-DRAFT": "0884abe17b5e3732fa29c976333d4e50cf304841d60e26000b22173efa49ac41",
    "MOHFW-STG-DRY-EYE-2016": "2034ac57f6c7b149fa20ec04e096ca9ba2e694037102e40bff29c6c244130267",
    "MOHFW-STG-ALCOHOL-DEPENDENCE-2016": "77a0f8fa83fb7bde3895dadd876c1e22b86a775c9438e380ea83cca02461226f",
    "MOHFW-STG-HYPERTENSION-2016": "8388906c4f3ce1beb4355d9c5fcc16f25dd96580532a78a5ab3e27e8f41b49da",
    "MOHFW-STG-MAJOR-TRAUMA-UNDATED": "bcdaa14b89629be96107d0b4526aabbe37425b46e41ab8ed2bb2cdbfa36171b2",
}

# Indian national programme guidelines (scripts/ingest_national_guidelines.py).
#
# Unlike the MoHFW batch this one is mostly infectious disease, and NCDC-NTG-AMR-2016
# is a national antimicrobial guideline in its own right -- the second such authority
# in the corpus, alongside ICMR and from a different issuing body.
NATIONAL = {
    "NCDC-NTG-AMR-2016": "15861464a570eb0d4aeb0cce7f88047e7361e2a36b32cf604a1418f3f83b817a",
    "NCDC-LEPTOSPIROSIS-2015": "a5b69959502df4a7e4fe43804e1f049b8b0d2c6812b673528fece74cd2b58a2e",
    "NCDC-RABIES-PROPHYLAXIS-2015": "c8c6cb6c88aa0377ea6c5cb114aea8adc12349290a01e81c60f7193ac2cf9951",
    "MOHFW-NVHCP-VIRAL-HEPATITIS-2018": "167d0852b0202fc2e0617a6358d8068fdc0135fec1f23fc364708eb36b09162c",
    "NVBDCP-MALARIA-DX-TX-2013": "3f6e8f9435cbe3671f70aa8ea8c47c18bcd8be23afdf180a8021edb1c914a766",
    "NVBDCP-AES-JE-2009": "56e38290807ad972f917c56ff5b5b7b525078daa08c79ff8101530288d977b7e",
    "NVBDCP-KALA-AZAR-ROADMAP-UNDATED": "d5ce5698af35c5f9d6e3653aff504fc814e4b5e21f34b2d907e7747c925e5666",
    "NVBDCP-LF-DRUG-DISTRIBUTORS-UNDATED": "bfaabe67dac15db640a4a628c32ff08d84c355f11b8775597ea6dfa1bebc9d85",
    "MOHFW-CHIKUNGUNYA-FACTS-2006": "7d958b7abb7c4942ae2b0c4020dffc29d4a3f4757e215d51b2fe29cf5ea76746",
    "NACO-MOHFW-RTI-STI-2014": "298c574e0b38154020de41f6675b2b1afcb847a343787e939ce5c4413c5ba869",
    "NLEP-DPMR-2012": "cf79605cdae2a9157eb4520627a33c197a1e7eb7987718c72e7e26f7a0a87cce",
    "NLEP-MO-TRAINING-MANUAL-2013": "7482844e1c1467c8003a02d6f8294589d5cbabe1e62979712beb944d169d683f",
    "NPPMBI-BURNS-UNDATED": "b2798ce89337b0f807b34aa46ac19068754977c0a0c9b095c7ec11e23d60a4c2",
    "NPCDCS-MO-MANUAL-UNDATED": "f45a65f2404fdcfcbcf5c3d943942af81c2662d13fa6c34ec77f8c6017acb181",
    "MOHFW-INTRAOCULAR-SURGERY-PRECAUTIONS-UNDATED":
        "55ee44a2283130395b26812e7edde602fd2b9bda3f5d1a4fe858b876eecd687d",
    "AYURVEDA-STG-UNATTRIBUTED-UNDATED":
        "153d5f8af97e8e1d5dd7ca4879bafdf6d1429e0cff5c46c57bda02afe7814aa5",
}


# The ICMR national corpus (scripts/ingest_icmr_national_corpus.py).
#
# The batch that changed what this corpus IS. Everything held before it was an
# antimicrobial or condition-specific treatment guideline; most of this batch is
# research-ethics governance, laboratory biosafety, programme policy, oncology
# consensus guidance and two research-activity compendia. Exactly one of its 55
# documents -- DHR-ICMR-RICKETTSIAL-2015 -- carries antimicrobial recommendations.

ICMR_NATIONAL = {
    "DHR-ICMR-RICKETTSIAL-2015":
        "38dbbc9154eca280244eefcba8e2ad1cef9e6472ad0167e6f0cbf678ed2d7c5f",
    "ICMR-BIOREPOSITORY-2026":
        "90bdede7f7ac09f3d06b54a1f713bfcbde8c02ec5ec9eaba59002cdce7707d7a",
    "ICMR-BSL3-GENERAL-UNDATED":
        "446803b42fd230987def5675f8be6656240bd9855f296bb8e0bfc1662d339126",
    "ICMR-BSL3-V3":
        "79e42e0288aebc5c6d46c084008b90425e6ea769eb79c65602b27aaa2d9678c7",
    "ICMR-CANCER-MONOGRAPH-2019":
        "9fdaf316746632f867cbe5e26d94d1bc7b53458890db49f21423c2de0a6599e3",
    "ICMR-CANCER-RESEARCH-NINETIES-UNDATED":
        "b0cec0882d6e3abbb87e1ad1772a12298ff0d874ad489cf5bd318aa3e4ff64d2",
    "ICMR-CELIAC-DISEASE-UNDATED":
        "2c35009de82614fc32d5150fcaa8c2478b726e2dc197652c38b9fad2613f7e58",
    "ICMR-CHIS-POLICY-2023":
        "5d1aab48dac635f8c4e2147a650899f2c13b58e46871b1319923b0983792d9b0",
    "ICMR-CONSENSUS-BREAST-2016":
        "a17b70025de98015cbdf41edc911eca384fff1aad07eecf6e80266f72b153c77",
    "ICMR-CONSENSUS-BUCCAL-MUCOSA-2014":
        "f7e9132bf05325b35f58f9a9ad6f5a6919cd8315cdccdb3a319fcc79285a5170",
    "ICMR-CONSENSUS-CERVIX-2016":
        "0dd2ea3c2f6d34098e9ed935b6affe45ef8f293edce0d962ed2f0e12e004cbaa",
    "ICMR-CONSENSUS-COLORECTAL-2014":
        "bd99625d402e21733d1f396d95fd45754e9245d2c4702c4f55a784d1cce6a839",
    "ICMR-CONSENSUS-ESOPHAGEAL-2017":
        "a248a5f9ea65efbf46e2dd2bc8cfdf998ca99ea1d8de77b791ee168eb937b891",
    "ICMR-CONSENSUS-GALLBLADDER-2014":
        "84733143fcf97a3dd714e7d65b0638de84593d6da4bac34d55b589c2ac7ca132",
    "ICMR-CONSENSUS-GASTRIC-2014":
        "8dfa77d9dce5e04134c7fcb96be332b80b010a0d62fa492a45c39002d5a4ae89",
    "ICMR-CONSENSUS-HEPATOCELLULAR-2019":
        "d078aadaa9728307a0e00ce26e4ac5dcaca96f0778a37740067493fb7eea04d3",
    "ICMR-CONSENSUS-LARYNX-HYPOPHARYNX-2017":
        "c5925068083159cf26d7d83ebdcb84503b56ef63e85414b4be912d08b05c3659",
    "ICMR-CONSENSUS-MDS-2019":
        "675b441700f07123528c03b11af450fc91300a349935f47a3001ebce304dff34",
    "ICMR-CONSENSUS-MYELOMA-2017":
        "bdb245701a85b1f24e5c76463e3f2d347e525c1f7c3f4a1e338f4f48c3fe6a46",
    "ICMR-CONSENSUS-NEUROENDOCRINE-2019":
        "7d959723e6d01c608ceda2aed26920e5fbc4054a3ff909a6dc9e72e1220ee289",
    "ICMR-CONSENSUS-NHL-HIGH-GRADE-2016":
        "d8d47c8aabc950b686c61565a8b46c4eb48163ffa558e009037319dc399b29e2",
    "ICMR-CONSENSUS-OVARIAN-2019":
        "4a72af4abcafb5d689b6306a4ddc8016a4ac5c31d2b30597d6c7311e782ec7c4",
    "ICMR-CONSENSUS-PAEDIATRIC-ONCOLOGY-2017":
        "8031d127c54847fe14af36d0eafb0115e0fdc050440dbb2940b20988b6d47573",
    "ICMR-CONSENSUS-PANCREATIC-2019":
        "33b65de12be73a941e032160307d53437fb73d7f3951f352365ae6483e009bfd",
    "ICMR-CONSENSUS-PROSTATE-2023":
        "9bc0c95380e746dd5dbfb10ef2e4fdccfdf084c5955798f0b09951fe8c7c9924",
    "ICMR-CONSENSUS-RETINOBLASTOMA-2023":
        "f74f484f640284de71aaeb59cd5f5ba438e540bf84bc2a88249e496b650410d4",
    "ICMR-CONSENSUS-SARCOMA-2016":
        "1dcf87f552bdc8b2c00a061f7c8dbb9b07508f3673f3058cb679ac3dbc434c9f",
    "ICMR-CONSENSUS-TONGUE-UNDATED":
        "89e96b335e81215f2f2fdbb46ec87b226095a893a2ffd410582a5178d76fa42c",
    "ICMR-CONSENSUS-URINARY-BLADDER-2024":
        "1fc65e9a3757157affe025da7f9a76f2b66a5d1f375f884d20bece0718a98c34",
    "ICMR-CONSENSUS-UTERINE-2019":
        "3830c422bc2b067d02b5eb476601126710d45471b5a754fc9fc15d17e4f4b56d",
    "ICMR-DBT-STEMCELL-RESEARCH-2013":
        "a6fafc9fbe20c45a2880f9202112b6a4bd4b1016249604c9429ac61a56ee9fb2",
    "ICMR-DBT-STEMCELL-RESEARCH-2017":
        "59fea55607f52d13905eeb6699416cd4f277d647d226eb377114c376c7779bbf",
    "ICMR-DNAR-CONSENSUS-2020":
        "d36fb43deb0073526b3ff787ec506d3ec350ff3c14763a137ddd2bd45bdf168e",
    "ICMR-ETHICS-2000":
        "d6aca66af4225e284c232edfd2224bd29b5f18c7b11f43174013a75a12bffc11",
    "ICMR-ETHICS-2006":
        "451309b2a9fbdaa4d9502c4a538f9a410e2f04102160930dd7e3e609ec660d24",
    "ICMR-ETHICS-AI-2023":
        "cb0e6845cd1cc11d494f9e18aa44d11f5f9dc3e55f84c6a87a9a8ffed7a24ef2",
    "ICMR-ETHICS-CHILDREN-2017":
        "e41dd026fb2b504e1f2ac6620a8286ddeb8f9bb12215973b9cce936b0f8fb6e8",
    "ICMR-ETHICS-HANDBOOK-2018":
        "d9e196320109db8963ce101a1ae1f4e0b62c3d854d54cd8d8615ee78452c730b",
    "ICMR-ETHICS-INTEGRATIVE-MEDICINE-ADDENDUM-2025":
        "9a3091c7ec57e2ee7e547707b3fc75f73d28c155db6401b5199b406fdeb89927",
    "ICMR-ETHICS-JOINT-REVIEW-2023":
        "a5096b25ae253f2474e0144552cf152aa36b4b1983a57f00443ea83a030b7f66",
    "ICMR-ETHICS-LAB-VALIDATION-2024":
        "ed3919f229eaa5cf1aa6a67f10507142d57438e6f7c7b5d9201f16a6a9bd85e5",
    "ICMR-ETHICS-NATIONAL-2017":
        "e610ab344a348f043a8e04b52a113e0d813aa44ccec2e585b6e536a9b145ba38",
    "ICMR-ETHICS-SYSTEMATIC-REVIEW-ADDENDUM-2024":
        "77655046d2afb0395777f4498a36bf98a8857e158833a38c420edc18edb6df22",
    "ICMR-HCT-2021":
        "9f62d09d8a7eebc8c10d9270285ff19098643e3e41c67f7e86c58946c95fcbcd",
    "ICMR-IAEC-FAQ-2025":
        "6a67fa1946215ae0c8f444092648bed0972b4b107f2efe771fad49e3ddd90cc6",
    "ICMR-IRISE-POLICY-2024":
        "c7248cd32f479a2b874ac114e6afbda98cc612b962681a4c335c4ca2a6ce9605",
    "ICMR-NCDC-NVBDCP-PESTICIDE-PROTOCOL-2014":
        "2b24c6729119c647c212ce2a1185b08a5b1b6f5b8a09d7977e591e0f0688234e",
    "ICMR-NCDC-NVBDCP-PESTICIDE-SOP-2014":
        "86766eb671c44082e7fd6537caf0028f4f65a128283c53976f51e1b2a6ed856d",
    "ICMR-SINGLE-ETHICS-REVIEW-FAQ-2026":
        "409c50db5a2e420094ea9d68f5eabb7c019607fb3e6211d3be21a00150870534",
    "ICMR-SOP-IMMUNOPHENOTYPING-2016":
        "b3a24ca04b7b88c1b2206ba6e520604c1ff3bb44d883d0271a16d97e60b4943d",
    "ICMR-STEMCELL-RESEARCH-2007":
        "9564f96da7e10c848a4f38db5b70225de03dfe085ede0ff2a7c11d6db29a5f57",
    "ICMR-STEMCELL-THERAPY-EVIDENCE-2021":
        "bf665ed3367698cf7fe89439e97cfda857533c794209bb3d07cb961f00d4b9d9",
    "ICMR-T1DM-2022":
        "f46289a1d9755ba570a6ac95d39acbb69b0d8ffaf72d42597aedb6423c433c6c",
    "ICMR-T2DM-2018":
        "d2dfa8e147e9f047bf11ff7b956a20ed67a034bda36cdf8d22ff4ff113d49d57",
    "MOHFW-ICMR-ETHICS-LEFTOVER-SAMPLES-2024":
        "76548bbc2358a8e58597a2510bbf5d78e91d0a6f80427449a59880a9425d58b0",
}

OFFICIAL.update(MOHFW)
OFFICIAL.update(NATIONAL)
OFFICIAL.update(ICMR_NATIONAL)

# Documents that are not clinical guidelines at all -- a community mass-drug-
# administration leaflet, a 2006 public fact sheet, and an unattributed Ayurvedic
# compilation. They are held below the clinical guidelines so they cannot sort
# alongside ICMR and NCDC in a precedence-ordered comparison.
UNRANKED_FOR_CLINICAL_USE = {
    "NVBDCP-LF-DRUG-DISTRIBUTORS-UNDATED",
    "MOHFW-CHIKUNGUNYA-FACTS-2006",
    "AYURVEDA-STG-UNATTRIBUTED-UNDATED",
}

# National programme documents whose own title page states no publication date.
NATIONAL_UNDATED = {
    "NVBDCP-KALA-AZAR-ROADMAP-UNDATED",
    "NVBDCP-LF-DRUG-DISTRIBUTORS-UNDATED",
    "MOHFW-CHIKUNGUNYA-FACTS-2006",
    "NPPMBI-BURNS-UNDATED",
    "NPCDCS-MO-MANUAL-UNDATED",
    "MOHFW-INTRAOCULAR-SURGERY-PRECAUTIONS-UNDATED",
    "AYURVEDA-STG-UNATTRIBUTED-UNDATED",
}

# The three MoHFW documents that DO carry antibiotic recommendations, each for its
# own condition only. Every other MoHFW document must declare that it carries none.
MOHFW_WITH_ANTIMICROBIAL_CONTENT = {
    "MOHFW-STG-ACUTE-SINUSITIS-UNDATED",
    "MOHFW-STG-PAED-RESP-INFECTIONS-2016",
    "MOHFW-STG-DIABETIC-FOOT-2016-DRAFT",
}

# MoHFW documents whose own title page states no publication date. A citation must
# say so rather than borrow a year from the file name or the PDF creation stamp.
MOHFW_UNDATED = {
    "MOHFW-STG-LBW-FEEDING-UNDATED",
    "MOHFW-STG-ACUTE-SINUSITIS-UNDATED",
    "MOHFW-STG-MAJOR-TRAUMA-UNDATED",
}

TRANSCRIBED = {
    "ICMR-STG-2022-23-CH05-IAI": PAGE_NONE,
    "ICMR-STG-2022-23-CH06-SSTI": PAGE_NONE,
    "ICMR-STG-2022-23-CH07-BJI": PAGE_NONE,
    "ICMR-STG-2022-23-CH08-CNS": PAGE_TRANSCRIPT,
    "ICMR-STG-2022-23-CH09-UTI": PAGE_TRANSCRIPT,
    "ICMR-STG-2022-23-CH10-HAI": PAGE_TRANSCRIPT,
    "ICMR-STG-2022-23-CH11-IMM": PAGE_TRANSCRIPT,
}


def _docs():
    out = {}
    for name in sorted(os.listdir(RAG_DIR)):
        if not name.endswith(".json"):
            continue
        with io.open(os.path.join(RAG_DIR, name), encoding="utf-8") as f:
            payload = json.load(f)
        out[payload["document"]["document_id"]] = payload
    return out


# ---------------------------------------------------------------------------
# Corpus composition
# ---------------------------------------------------------------------------

def test_corpus_holds_every_expected_document():
    docs = _docs()
    expected = list(OFFICIAL) + list(TRANSCRIBED)
    assert len(docs) == len(expected) == 94
    for doc_id in expected:
        assert doc_id in docs, f"{doc_id} missing from the corpus"


def test_official_documents_keep_their_verified_hashes():
    docs = _docs()
    for doc_id, digest in OFFICIAL.items():
        doc = docs[doc_id]["document"]
        assert doc["file_sha256"] == digest, f"{doc_id} hash changed"
        assert doc.get("source_type", "OFFICIAL_PDF") == "OFFICIAL_PDF"
        assert doc.get("page_reference_kind", PAGE_OFFICIAL) == PAGE_OFFICIAL
        assert doc.get("provenance_basis", "HASH_VERIFIED_PDF") == "HASH_VERIFIED_PDF"
        assert doc["page_count"] and doc["page_count"] > 0


def test_transcriptions_declare_themselves_as_such():
    docs = _docs()
    for doc_id, page_kind in TRANSCRIBED.items():
        doc = docs[doc_id]["document"]
        assert doc["source_type"] in (
            "GOOGLE_DOCS_EXPORT_TRANSCRIPTION", "PLAIN_TEXT_TRANSCRIPTION")
        assert doc["page_reference_kind"] == page_kind
        assert doc["provenance_basis"] == "OPERATOR_ATTESTATION"
        assert "OPERATOR-ATTESTED EDITION, NOT VERIFIED" in doc["notes"]
        # The hash identifies the transcription, and the note must not let that
        # be read as confirmation of the edition.
        assert len(doc["file_sha256"]) == 64
        assert "SHA-256 identifies the transcription, not the edition" in doc["notes"]


def test_plain_text_documents_carry_no_page_numbers_at_all():
    docs = _docs()
    for doc_id, page_kind in TRANSCRIBED.items():
        if page_kind != PAGE_NONE:
            continue
        payload = docs[doc_id]
        assert payload["document"]["page_count"] is None
        for chunk in payload["chunks"]:
            assert chunk["page"] is None, (
                f"{doc_id} synthesised a page number for an unpaginated text file"
            )


def test_no_transcription_claims_to_be_a_hash_verified_pdf():
    for doc_id, payload in _docs().items():
        doc = payload["document"]
        if doc.get("source_type", "OFFICIAL_PDF") == "OFFICIAL_PDF":
            continue
        assert doc["provenance_basis"] != "HASH_VERIFIED_PDF"
        assert doc["page_reference_kind"] != PAGE_OFFICIAL


def test_edition_claim_is_marked_unverified_on_every_2022_23_chapter():
    docs = _docs()
    for doc_id in TRANSCRIBED:
        doc = docs[doc_id]["document"]
        assert "2022-23" in doc["version"]
        assert "unverified" in doc["version"].lower()
        assert "No official 2022-23 PDF is held" in doc["notes"]


# ---------------------------------------------------------------------------
# MoHFW STG scope declarations
#
# These documents are the reason a scope declaration is not decoration. A
# hypertension or dry eye guideline sitting at the same precedence rank as ICMR
# will surface on some query eventually, and the note is what tells the reader it
# has no standing on antimicrobial choice.
# ---------------------------------------------------------------------------

def test_every_mohfw_document_declares_its_antimicrobial_scope():
    docs = _docs()
    for doc_id in MOHFW:
        notes = docs[doc_id]["document"]["notes"]
        if doc_id in MOHFW_WITH_ANTIMICROBIAL_CONTENT:
            assert "CONTAINS ANTIMICROBIAL RECOMMENDATIONS" in notes, doc_id
            # Naming the agents is not enough: the note must also say which source
            # governs when they differ from ICMR or the local antibiogram.
            assert "governing sources" in notes, doc_id
        else:
            assert "NOT AN ANTIMICROBIAL STEWARDSHIP SOURCE" in notes, doc_id
            assert "never be cited for antimicrobial choice" in notes, doc_id


def test_undated_mohfw_documents_do_not_invent_a_publication_date():
    docs = _docs()
    for doc_id in MOHFW_UNDATED:
        doc = docs[doc_id]["document"]
        assert "NOT STATED IN THE DOCUMENT" in doc["publication_date"], doc_id
        # A file name or a PDF creation stamp is evidence of drafting, not of
        # publication, and must never be promoted into a bare year.
        assert not doc["publication_date"].strip().startswith("20"), doc_id


def test_the_draft_is_labelled_a_draft_everywhere_a_reader_looks():
    doc = _docs()["MOHFW-STG-DIABETIC-FOOT-2016-DRAFT"]["document"]
    assert "DRAFT" in doc["title"]
    assert "DRAFT" in doc["version"]
    assert "draft" in doc["publication_date"]
    assert "must be labelled a draft" in doc["notes"]


def test_inferred_attribution_is_never_stated_as_printed_attribution():
    docs = _docs()
    for doc_id in ("MOHFW-STG-NEONATAL-JAUNDICE-2016", "MOHFW-STG-LBW-FEEDING-UNDATED"):
        doc = docs[doc_id]["document"]
        org, notes = doc["issuing_org"], doc["notes"]
        assert ("NOT NAMED ON THE DOCUMENT" in org
                or "No ministry imprint appears on the title page" in org), doc_id
        # Both files still carry unresolved editorial placeholders.
        assert ("WORKING COPY, NOT A FINAL PUBLICATION" in notes
                or "UNDATED AND UNFINISHED" in notes), doc_id


def test_mohfw_source_urls_do_not_claim_a_location_that_was_never_verified():
    docs = _docs()
    for doc_id in MOHFW:
        doc = docs[doc_id]["document"]
        assert doc["source_url"] == "https://www.mohfw.gov.in/", doc_id
        assert "could not be verified" in doc["notes"], doc_id


# ---------------------------------------------------------------------------
# National programme guideline scope declarations
#
# This batch is mostly infectious disease, so "does it carry antimicrobial guidance"
# is no longer a yes/no question: an antimalarial policy, an antiviral guideline, a
# rabies prophylaxis schedule and a leprosy MDT regimen are four different answers
# and none of them means "empirical antibacterial selection". Each document must
# therefore say which it is.
# ---------------------------------------------------------------------------

# Every recognised way a document may describe its own antimicrobial scope. A new
# document with none of these has not declared one, which is the failure this catches.
_SCOPE_MARKERS = (
    "PRIMARY ANTIMICROBIAL SOURCE",
    "ANTIMICROBIAL RECOMMENDATIONS",
    "NOT AN ANTIMICROBIAL STEWARDSHIP SOURCE",
    "NOT ANTIBACTERIAL THERAPY",
    "ANTIVIRAL THERAPY ONLY",
    "ANTIMALARIAL DRUG POLICY",
    "ANTIMICROBIAL-RELEVANT",
    "ANTIPARASITIC DRUGS",
    "not an antimicrobial selection guideline",
    "any antimicrobial choice",
    "cited for antimicrobial choice",
)

# Documents carrying antimicrobial recommendations that are NOT themselves a national
# antimicrobial authority, and so must name what governs when they differ from one.
NATIONAL_CITING_GOVERNING_SOURCES = {
    "NCDC-LEPTOSPIROSIS-2015",
    "NVBDCP-AES-JE-2009",
    "NACO-MOHFW-RTI-STI-2014",
    "NPPMBI-BURNS-UNDATED",
    "MOHFW-INTRAOCULAR-SURGERY-PRECAUTIONS-UNDATED",
}


def test_every_national_document_declares_its_antimicrobial_scope():
    docs = _docs()
    for doc_id in NATIONAL:
        notes = docs[doc_id]["document"]["notes"]
        assert any(m in notes for m in _SCOPE_MARKERS), (
            f"{doc_id} does not declare what antimicrobial content it carries"
        )


def test_documents_deferring_to_a_national_authority_name_which_one():
    docs = _docs()
    for doc_id in NATIONAL_CITING_GOVERNING_SOURCES:
        notes = docs[doc_id]["document"]["notes"]
        assert "ICMR" in notes and "NCDC-NTG-AMR-2016" in notes, doc_id
        assert "local hospital antibiogram" in notes, doc_id


def test_the_second_national_antimicrobial_authority_declares_the_overlap():
    """
    Holding two national antimicrobial guidelines from two bodies is a real change in
    what the corpus can say. It must not be silent about the fact that they can differ,
    and it must not imply this system picks a winner.
    """
    doc = _docs()["NCDC-NTG-AMR-2016"]["document"]
    notes = doc["notes"]
    assert "TWO NATIONAL AUTHORITIES ARE NOW HELD" in notes
    assert "Neither supersedes the other" in notes
    assert "no adjudication between them is performed" in notes
    # Ingestion adds evidence; it must not be read as having changed a clinical rule.
    assert "changes no rule" in notes
    assert doc["precedence_rank"] == 2


def test_undated_national_documents_do_not_invent_a_publication_date():
    docs = _docs()
    for doc_id in NATIONAL_UNDATED:
        doc = docs[doc_id]["document"]
        assert "NOT STATED IN THE DOCUMENT" in doc["publication_date"], doc_id
        assert not doc["publication_date"].strip().startswith("20"), doc_id


def test_non_guideline_documents_rank_below_the_clinical_guidelines():
    docs = _docs()
    for doc_id in NATIONAL:
        rank = docs[doc_id]["document"]["precedence_rank"]
        if doc_id in UNRANKED_FOR_CLINICAL_USE:
            assert rank == 4, f"{doc_id} should not sort alongside ICMR and NCDC"
        else:
            assert rank == 2, doc_id


def test_the_ayurvedic_compilation_declares_what_it_is_and_what_it_is_not():
    doc = _docs()["AYURVEDA-STG-UNATTRIBUTED-UNDATED"]["document"]
    notes = doc["notes"]
    assert "NOT NAMED ANYWHERE IN THE DOCUMENT" in doc["issuing_org"]
    assert "TRADITIONAL MEDICINE (AYURVEDA), NOT ALLOPATHIC GUIDANCE" in notes
    assert "WEAKEST PROVENANCE IN THE CORPUS" in notes
    # The safety analysis that surrounds the allopathic corpus does not apply here,
    # and a passage retrieved from this file must not look as though it does.
    assert "no interaction, dosing or safety checking for Ayurvedic preparations" in notes
    # No issuer means no issuer website; inventing one would manufacture provenance.
    assert doc["source_url"] == ""


def test_commercial_sponsorship_in_a_source_is_disclosed_not_hidden():
    notes = _docs()["NLEP-DPMR-2012"]["document"]["notes"]
    assert "COMMERCIAL SPONSOR ACKNOWLEDGED IN THE SOURCE" in notes
    assert "Novartis" in notes


# ---------------------------------------------------------------------------
# Citation rendering
# ---------------------------------------------------------------------------

def _chunk_for(document_id):
    vector_store.load()
    for c in vector_store.chunks:
        if c["document_id"] == document_id:
            return c
    pytest.skip(f"no chunks loaded for {document_id}")


def _retrieved(document_id):
    from backend.rag.store import RetrievedChunk

    doc = vector_store.docs[document_id]
    c = _chunk_for(document_id)
    return RetrievedChunk(
        document_id=document_id,
        document_title=doc.get("title", ""),
        issuing_org=doc.get("issuing_org", ""),
        geographic_scope=doc.get("geographic_scope", ""),
        version=doc.get("version", ""),
        publication_date=doc.get("publication_date", ""),
        source_url=doc.get("source_url", ""),
        page=c.get("page"),
        section=c.get("section"),
        text=c["text"],
        score=0.9,
        notes=doc.get("notes", ""),
        source_type=doc.get("source_type", "OFFICIAL_PDF"),
        page_reference_kind=doc.get("page_reference_kind", PAGE_OFFICIAL),
        provenance_basis=doc.get("provenance_basis", "HASH_VERIFIED_PDF"),
    )


def test_official_pages_render_as_plain_page_citations():
    cit = _retrieved("ICMR-STW-VOL3-2022").to_citation()
    assert "p. " in cit["section_page"]
    assert "transcript" not in cit["section_page"]
    assert "NOT an official page" not in cit["section_page"]
    assert cit["page_reference_kind"] == PAGE_OFFICIAL


def test_transcript_pages_are_never_rendered_as_official_pages():
    cit = _retrieved("ICMR-STG-2022-23-CH10-HAI").to_citation()
    assert "transcript p." in cit["section_page"]
    assert "NOT an official page of this edition" in cit["section_page"]
    assert cit["page_reference_kind"] == PAGE_TRANSCRIPT
    assert cit["provenance_basis"] == "OPERATOR_ATTESTATION"
    assert "OPERATOR-ATTESTED EDITION, NOT VERIFIED" in cit["provenance_note"]


def test_unpaginated_text_renders_no_page_locator():
    cit = _retrieved("ICMR-STG-2022-23-CH07-BJI").to_citation()
    assert "no pagination" in cit["section_page"]
    assert "p. " not in cit["section_page"].replace("no pagination", "")
    assert cit["page_reference_kind"] == PAGE_NONE


def test_every_citation_carries_its_provenance_basis():
    vector_store.load()
    for doc_id in vector_store.docs:
        cit = _retrieved(doc_id).to_citation()
        assert cit["provenance_basis"] in ("HASH_VERIFIED_PDF", "OPERATOR_ATTESTATION")
        assert cit["page_reference_kind"] in (PAGE_OFFICIAL, PAGE_TRANSCRIPT, PAGE_NONE)
        assert cit["verbatim_passage"]


# ---------------------------------------------------------------------------
# Index integrity
# ---------------------------------------------------------------------------

def test_vector_index_is_aligned_with_the_expanded_corpus():
    store = GuidelineVectorStore()
    assert store.load() is True, (
        "the vector index is missing or misaligned with the corpus; rebuild it with "
        "GuidelineVectorStore().build() after any ingestion"
    )
    assert store.available
    assert len(store.chunks) == store.matrix.shape[0]
    assert len(store.docs) == 94


def test_new_chapters_are_actually_retrievable():
    vector_store.load()
    ids = [d for d in vector_store.docs if d.startswith("ICMR-STG-2022-23")]
    assert len(ids) == 7

    hits = vector_store.search("catheter associated urinary tract infection", k=3, document_ids=ids)
    assert hits, "the ingested 2022-23 chapters returned nothing"
    assert all(h.document_id in ids for h in hits)


def test_mohfw_documents_are_retrievable_on_their_own_subject():
    vector_store.load()
    ids = [d for d in vector_store.docs if d.startswith("MOHFW-STG-")]
    assert len(ids) == 12

    hits = vector_store.search("blood pressure target in adults with hypertension", k=3,
                               document_ids=ids)
    assert hits, "the ingested MoHFW documents returned nothing"
    assert hits[0].document_id == "MOHFW-STG-HYPERTENSION-2016"
    # A genuine page of a genuine document, not a transcript page.
    assert hits[0].page_reference_kind == PAGE_OFFICIAL
    assert hits[0].page and hits[0].page > 0


def test_adding_non_antimicrobial_documents_did_not_displace_the_antimicrobial_corpus():
    """
    Twelve mostly non-antimicrobial documents now sit at the same precedence rank as
    ICMR. That is safe only while an antimicrobial question still resolves to an
    antimicrobial source, so the top hit is checked rather than assumed.
    """
    vector_store.load()
    # NCDC-NTG-AMR-2016 belongs here too: it is a national antimicrobial guideline,
    # so an antimicrobial query resolving to it is a correct answer, not displacement.
    antimicrobial_corpus = {
        d for d in vector_store.docs
        if d.startswith(("ICMR-", "WHO-")) or d == "NCDC-NTG-AMR-2016"
    }
    for query in (
        "empirical antibiotic therapy for hospital acquired pneumonia",
        "WHO AWaRe reserve group antibiotics",
        "nitrofurantoin in renal impairment",
    ):
        hits = vector_store.search(query, k=3)
        assert hits, query
        assert hits[0].document_id in antimicrobial_corpus, (
            f"{query!r} now resolves to {hits[0].document_id}, which is not an "
            f"antimicrobial source"
        )


def test_national_programme_documents_are_retrievable_on_their_own_subject():
    vector_store.load()
    for query, expected in (
        ("syndromic empirical therapy for bacterial dysentery", "NCDC-NTG-AMR-2016"),
        ("syndromic management of vaginal discharge", "NACO-MOHFW-RTI-STI-2014"),
        ("multi drug therapy regimen for multibacillary leprosy",
         "NLEP-MO-TRAINING-MANUAL-2013"),
    ):
        hits = vector_store.search(query, k=3)
        assert hits, query
        assert hits[0].document_id == expected, (
            f"{query!r} resolved to {hits[0].document_id}, expected {expected}"
        )
        assert hits[0].page_reference_kind == PAGE_OFFICIAL
        assert hits[0].page and hits[0].page > 0


def test_the_ayurvedic_compilation_does_not_surface_on_antibacterial_questions():
    """
    The one document in the corpus for which this system performs no safety analysis
    at all. It must stay out of the way of drug questions rather than being offered
    as though it were part of the allopathic evidence base.
    """
    vector_store.load()
    for query in (
        "empirical antibiotic for community acquired pneumonia",
        "amoxicillin dose in renal impairment",
        "which antibiotic for urinary tract infection",
    ):
        hits = vector_store.search(query, k=5)
        assert "AYURVEDA-STG-UNATTRIBUTED-UNDATED" not in [h.document_id for h in hits], query


def test_retrieval_still_refuses_off_domain_queries():
    """Expanding the corpus must not weaken the refusal path."""
    from backend.rag.retrieve import retrieve

    result = retrieve("how do I change a bicycle tyre", k=3).to_dict()
    assert result["refused"] is True
    assert not result["retrieved"]


# ---------------------------------------------------------------------------
# Clinical domain
#
# The axis the ICMR national corpus made necessary. Precedence rank says how much
# weight a document carries in a clinical conflict; it cannot say what the document
# is authoritative ABOUT, and once research-ethics guidelines and oncology consensus
# documents joined the corpus, that second question became the one that decides
# whether a passage may be offered as prescribing evidence at all.
# ---------------------------------------------------------------------------

def test_every_document_declares_a_known_clinical_domain():
    docs = _docs()
    for doc_id, payload in docs.items():
        domain = payload["document"].get("clinical_domain")
        assert domain, f"{doc_id} declares no clinical_domain"
        assert domain in DOMAIN_READING_CONTRACT, f"{doc_id} has unknown domain {domain}"


def test_only_genuine_antimicrobial_sources_claim_the_antimicrobial_domain():
    """
    The default for this field is ANTIMICROBIAL_TREATMENT, so that adding it changed
    nothing for documents that predate it. That default is correct for the primary
    antimicrobial sources and FALSE for everything else, which is why the legacy
    corpus was backfilled (scripts/backfill_clinical_domains.py). This test is what
    stops the default quietly reasserting itself: a dry eye guideline, an oncology
    consensus document or a research-ethics guideline labelled ANTIMICROBIAL_TREATMENT
    would be the corpus claiming antimicrobial authority it does not have.
    """
    docs = _docs()
    claiming = {
        doc_id for doc_id, p in docs.items()
        if p["document"]["clinical_domain"] == DOMAIN_ANTIMICROBIAL
    }
    assert claiming == {
        "ICMR-STG-2019-ED2",
        "NCDC-NTG-AMR-2016",
        "WHO-AWARE-BOOK-2022",
        "ICMR-STG-2022-23-CH05-IAI",
        "ICMR-STG-2022-23-CH06-SSTI",
        "ICMR-STG-2022-23-CH07-BJI",
        "ICMR-STG-2022-23-CH08-CNS",
        "ICMR-STG-2022-23-CH09-UTI",
        "ICMR-STG-2022-23-CH10-HAI",
        "ICMR-STG-2022-23-CH11-IMM",
        "DHR-ICMR-RICKETTSIAL-2015",
    }


def test_non_clinical_documents_are_ranked_below_every_clinical_guideline():
    """Ethics, laboratory, policy and report documents never sort with the guidelines."""
    docs = _docs()
    for doc_id, payload in docs.items():
        doc = payload["document"]
        if doc["clinical_domain"] in CLINICAL_DOMAINS:
            continue
        assert doc["precedence_rank"] == NOT_A_CLINICAL_GUIDELINE_RANK, (
            f"{doc_id} is {doc['clinical_domain']} but sits at rank "
            f"{doc['precedence_rank']}, where it would sort alongside ICMR and NCDC"
        )


def test_every_non_antimicrobial_passage_carries_its_reading_contract():
    """
    A retrieved passage must say what kind of document it came from. Without this a
    research-ethics passage and an ICMR antimicrobial passage are rendered with
    identical citation furniture.
    """
    vector_store.load()
    hits = vector_store.search("informed consent of participants in research", k=5)
    assert hits, "expected the research ethics documents to be retrievable"
    for hit in hits:
        if hit.clinical_domain == DOMAIN_ANTIMICROBIAL:
            continue
        citation = hit.to_citation()
        assert citation["domain_caveat"], hit.document_id
        assert citation["carries_antimicrobial_authority"] is False, hit.document_id


def test_a_research_ethics_question_is_never_answered_as_clinical_evidence():
    """
    The corpus now holds 14 research-ethics documents. They are retrievable on
    purpose, and every answer drawn from them must state that they govern research
    conduct rather than patient care.
    """
    from backend.rag.retrieve import retrieve

    result = retrieve("ethical requirements for an institutional ethics committee", k=4)
    if result.refused:
        pytest.skip("the ethics documents did not clear the relevance floor for this query")
    assert result.chunks
    assert not any(c.carries_antimicrobial_authority for c in result.chunks)
    caveats = " ".join(result.caveats())
    assert "NO PASSAGE RETRIEVED HERE CARRIES ANTIMICROBIAL RECOMMENDATIONS" in caveats


def test_the_no_antimicrobial_caveat_does_not_fire_when_the_corpus_did_answer():
    """
    The caveat is gated on antimicrobial CONTENT, not on the antimicrobial DOMAIN.
    NCDC-LEPTOSPIROSIS-2015 is condition-specific and does carry doxycycline
    recommendations; telling a reader the corpus had not answered a leptospirosis
    question it had just answered would be a false statement about the corpus.
    """
    from backend.rag.retrieve import retrieve

    result = retrieve("leptospirosis doxycycline treatment", k=4)
    if result.refused:
        pytest.skip("leptospirosis query did not clear the relevance floor")
    caveats = " ".join(result.caveats())
    assert "NO PASSAGE RETRIEVED HERE CARRIES ANTIMICROBIAL RECOMMENDATIONS" not in caveats


def test_a_prescription_record_never_entered_the_guideline_corpus():
    """
    Two of the files supplied with the ICMR batch were this system's own generated
    patient prescription records, not guidelines. Ingesting them would have put
    patient-visit content into the corpus that answers clinical questions.
    """
    docs = _docs()
    for doc_id, payload in docs.items():
        doc = payload["document"]
        assert "PATIENT-" not in doc_id
        assert "Prescription_PATIENT" not in doc.get("source_file", "")
    vector_store.load()
    hits = vector_store.search("prescribing clinician visit id patient id", k=5)
    for hit in hits:
        assert "PATIENT-" not in hit.text or "PRESCRIPTION" not in hit.text.upper()[:60]


# ---------------------------------------------------------------------------
# Guards that the corpus expansion weakened
#
# Both of these broke when the corpus grew from 39 to 94 documents, and neither
# broke visibly: the system kept answering, just less safely. They are pinned here
# because the next expansion will pull on them the same way.
# ---------------------------------------------------------------------------

def test_an_invented_drug_name_is_still_caught_by_the_vocabulary_guard():
    """
    The relevance floor cannot separate these -- a nonsense name inside a
    well-formed dosing question matches on sentence FORM. unknown_entities() is the
    check that does, and a larger vocabulary weakens it: at 94 documents the corpus
    contains "fiction", and "fictionalcillin" was being accepted as an inflection of
    it across an eight-character suffix.
    """
    from backend.rag.retrieve import unknown_entities

    vector_store.load()
    for invented in ("fictionalcillin", "zzzzmycin", "flurbamycin", "blorbotrexate"):
        assert unknown_entities(f"{invented} dosing in adults") == [invented], invented


def test_ordinary_clinical_inflections_are_not_mistaken_for_invented_names():
    """The bound that fixed the above must not start rejecting real questions."""
    from backend.rag.retrieve import unknown_entities

    vector_store.load()
    for query in (
        "nitrofurantoin renal impairment",
        "renally cleared antibiotics",
        "contraindications in pregnancy",
        "carbapenem resistant enterobacteriaceae treatment",
        "hepatotoxicity of isoniazid",
        "informed consent in biomedical research",
    ):
        assert unknown_entities(query) == [], query


def test_a_question_about_a_guideline_the_corpus_does_not_hold_is_refused():
    """
    Spec 23. The words in such a question are ordinary, so the vocabulary guard has
    nothing to object to and the passages that come back are real, correctly
    attributed text about the clinical topic. Returning them under a question that
    names a different, non-existent document invites the reader to believe that
    document exists and says this.
    """
    from backend.rag.retrieve import retrieve, unknown_document_reference

    vector_store.load()
    for query in (
        "What does the Fictional Guideline 2099 recommend for sepsis?",
        "What do the Fictional Guidelines say about sepsis?",
        "What does the Atlantis Protocol 2050 recommend?",
    ):
        assert unknown_document_reference(query), query
        result = retrieve(query, k=3)
        assert result.refused, query
        assert not result.chunks, query


def test_questions_naming_documents_the_corpus_does_hold_are_not_refused():
    """The check above must not fire on the corpus's own documents."""
    from backend.rag.retrieve import retrieve, unknown_document_reference

    vector_store.load()
    for query in (
        "What do the ICMR guidelines 2019 recommend for sepsis?",
        "ICMR treatment guidelines for urinary tract infection",
        "national guidelines for stem cell research",
        "consensus document for management of breast cancer",
        "MoHFW guidelines 2016 for snakebite",
        "what do the guidelines recommend for sepsis",
        "Which antibiotic do the guidelines recommend for enteric fever?",
    ):
        assert unknown_document_reference(query) is None, query
        assert not retrieve(query, k=3).refused, query


def test_a_near_tie_is_broken_towards_clinical_standing():
    """
    The ICMR cancer research compendium outscored the NACO RTI/STI guideline by
    0.0009 on 'syndromic management of vaginal discharge', on a passage describing a
    Phase-I trial. Both are still returned; the guideline leads.
    """
    vector_store.load()
    hits = vector_store.search("syndromic management of vaginal discharge", k=5)
    assert hits
    assert hits[0].document_id == "NACO-MOHFW-RTI-STI-2014"
    ids = [h.document_id for h in hits]
    assert "ICMR-CANCER-MONOGRAPH-2019" in ids, (
        "the tie-break must reorder, not suppress: the research compendium is still "
        "retrievable and still carries its own domain caveat"
    )
