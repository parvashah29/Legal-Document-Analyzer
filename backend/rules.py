"""Deterministic clause-risk rules. Each rule is a regex pattern set plus canned explanation text.
An LLM (if available) only enriches the wording; the detection and severity come from here so the
result is auditable and works fully offline."""
import re
from dataclasses import dataclass, field


@dataclass
class Rule:
    key: str
    clause_type: str
    severity: int
    plain_english: str
    concerns: list
    rewrite: str
    tip: str
    patterns: list
    # (regex, new_severity): if the regex matches the chunk, severity is raised to new_severity
    escalate: list = field(default_factory=list)
    # if this regex matches the chunk the rule is downgraded to `mitigated_severity`
    mitigate: str | None = None
    mitigated_severity: int = 3
    supersedes: list = field(default_factory=list)  # rule keys suppressed when this one fires in the same chunk

    def __post_init__(self):
        self.patterns = [re.compile(p, re.I) for p in self.patterns]
        self.escalate = [(re.compile(p, re.I), s) for p, s in self.escalate]
        self.mitigate = re.compile(self.mitigate, re.I) if self.mitigate else None


def level_for(sev: int) -> str:
    return "high" if sev >= 7 else "medium" if sev >= 4 else "low"


RULES = [
    Rule("unlimited_liability", "Unlimited Liability", 9,
         "One party's financial exposure under this contract has no ceiling, so a single dispute could cost far more than the contract is worth.",
         ["Ask for a liability cap tied to fees paid or contract value.", "Check that the exposure is not one-sided."],
         "Each Party's total aggregate liability under this Agreement shall not exceed the fees paid or payable in the 12 months preceding the claim.",
         "Can we cap liability at the total fees paid so neither side carries unlimited exposure?",
         [r"unlimited\s+liabilit", r"liabilit\w*\s+(?:\w+\s+){0,4}(?:shall\s+be|is|are|will\s+be)\s+unlimited",
          r"(?:no|without\s+(?:any\s+)?)\s*(?:cap|limit|limitation)s?\s+(?:on|to|of)\s+(?:its\s+|their\s+|the\s+)?liabilit",
          r"not\s+(?:be\s+)?(?:subject\s+to|limited\s+by)\s+any\s+(?:cap|limit)",
          r"liabilit\w*\s+(?:\w+\s+){0,6}(?:without|shall\s+not\s+be\s+subject\s+to)\s+(?:any\s+)?(?:limit|cap)"],
         supersedes=["liability_cap"]),
    Rule("liability_cap", "Limitation of Liability", 5,
         "Limits how much money can be recovered if the other side breaches or causes harm.",
         ["Check the cap amount is meaningful relative to the contract value.", "Confirm the cap and the damages exclusions apply to both parties."],
         "Neither Party shall be liable for indirect or consequential damages. Each Party's aggregate liability shall not exceed the greater of the fees paid in the prior 12 months or $50,000.",
         "Let's make the liability cap mutual and proportional to contract value.",
         [r"limitation\s+of\s+liabilit", r"in\s+no\s+event\s+shall", r"aggregate\s+liabilit", r"consequential\s+damages",
          r"liabilit\w*\s+(?:\w+\s+){0,6}(?:shall\s+not\s+exceed|limited\s+to)"],
         escalate=[(r"(?:shall\s+not\s+exceed|limited\s+to)\s+(?:the\s+(?:sum|amount)\s+of\s+)?(?:\$|USD\s*)?\s*(?:1|one|10|ten|100|one\s+hundred)\b(?!\d|,)", 8)]),
    Rule("indemnification", "Indemnification", 5,
         "You agree to cover the other party's legal costs and losses in certain situations.",
         ["Check whether indemnity is mutual.", "Limit it to direct damages from your own breach or negligence, not any claim at all."],
         "Each Party shall indemnify and hold harmless the other from third-party claims arising from the indemnifying Party's negligence, willful misconduct or material breach, subject to the liability cap.",
         "I'd like the indemnity to be mutual and subject to the same cap as other liability.",
         [r"indemnif", r"hold\s+harmless"],
         escalate=[(r"any\s+and\s+all\s+(?:claims|losses|damages|liabilit)", 8),
                   (r"even\s+if\s+(?:such\s+)?(?:\w+\s+){0,8}(?:caused|arising)[^.]{0,60}(?:negligence|misconduct)\s+of\s+(?:the\s+)?(?:client|company|customer|licensor|landlord)", 9),
                   (r"(?:caused\s+in\s+part\s+by|even\s+if)[^.]{0,80}negligence", 9)],
         mitigate=r"(?:each|either)\s+party|mutual(?:ly)?", mitigated_severity=4),
    Rule("auto_renewal", "Automatic Renewal", 7,
         "The contract renews on its own unless you cancel inside a specific window, so you can be locked into another term without noticing.",
         ["Note the cancellation deadline and put it in your calendar.", "Look for a long notice period or a renewal price increase."],
         "This Agreement renews for successive one-year terms only if both Parties confirm in writing; either Party may opt out with 30 days' notice.",
         "Can renewal require written confirmation, or at least shorten the opt-out notice window?",
         [r"automatic(?:ally)?\s+(?:\w+\s+){0,3}renew", r"auto-?\s?renew", r"renew\w*\s+automatically", r"evergreen",
          r"successive\s+(?:renewal\s+)?(?:terms?|periods?)\s+of"],
         escalate=[(r"(?:ninety|90|one\s+hundred\s+(?:and\s+)?eighty|180|sixty|60)\s*(?:\(\d+\)\s*)?days", 8)]),
    Rule("one_sided_termination", "One-Sided Termination", 8,
         "Only one party can walk away freely (or end the deal on short notice) while you stay bound.",
         ["Ask for equal termination rights for both parties.", "Check for early-termination fees and what survives termination."],
         "Either Party may terminate this Agreement for convenience on 30 days' written notice, or for cause if a material breach remains uncured 15 days after notice.",
         "I'd like termination rights to be reciprocal, with a notice period and a cure window.",
         [r"(?:client|company|provider|licensor|employer|landlord|customer|owner|supplier|vendor|disclosing\s+party)\b[^.]{0,80}"
          r"(?:may|can|shall\s+have\s+the\s+right\s+to|reserves\s+the\s+right\s+to)\s+terminate[^.]{0,120}"
          r"(?:sole\s+discretion|for\s+any\s+(?:reason|or\s+no\s+reason)|without\s+(?:cause|notice|liabilit)|at\s+any\s+time)"],
         mitigate=r"(?:either|each|both)\s+part(?:y|ies)\s+(?:may|can|has)\s+(?:the\s+right\s+to\s+)?terminate", mitigated_severity=4,
         supersedes=["termination"]),
    Rule("termination", "Termination", 4,
         "Explains how and when the agreement can be ended.",
         ["Confirm notice periods and any termination fees.", "Make sure confidentiality and payment duties that survive termination are clear."],
         "Either Party may terminate for convenience on 30 days' written notice, or for uncured material breach.",
         "Can we agree equal termination rights with a reasonable cure period?",
         [r"(?:may|right\s+to|shall\s+have\s+the\s+right\s+to)\s+terminate", r"termination\s+(?:for|of|by)", r"upon\s+termination"]),
    Rule("non_compete", "Non-Compete", 8,
         "Restricts you from working for competitors or starting a competing business for some time or area.",
         ["Check the duration and geographic scope.", "Non-competes may be unenforceable in some jurisdictions; get local advice."],
         "For 6 months after termination, the Contractor shall not directly solicit clients served under this Agreement. This does not restrict general professional activity.",
         "I'd like to narrow the non-compete to a non-solicit of specific clients for six months.",
         [r"non-?\s?compet", r"covenant\s+not\s+to\s+compete", r"shall\s+not\s+(?:directly\s+or\s+indirectly\s+)?(?:\w+\s+){0,3}compet",
          r"(?:not|never)\s+(?:to\s+)?(?:directly\s+or\s+indirectly\s+)?(?:engage|work|be\s+employed|participate)[^.]{0,100}(?:compet)"],
         escalate=[(r"worldwide|global|nationwide|(?:two|three|four|five|[2-9])\s*(?:\(\d+\)\s*)?years?|perpetual", 9)]),
    Rule("non_solicit", "Non-Solicitation", 4,
         "Stops you from recruiting the other party's employees or clients for a period.",
         ["Check the duration.", "Ensure general advertising is not treated as solicitation."],
         "For 12 months after termination neither Party shall actively solicit the other's employees, excluding responses to general advertisements.",
         "Please make the non-solicit mutual and exclude general job postings.",
         [r"non-?\s?solicit", r"shall\s+not\s+(?:directly\s+or\s+indirectly\s+)?solicit"]),
    Rule("ip_assignment", "Intellectual Property Assignment", 8,
         "Ownership of what you create transfers to the other party.",
         ["Check that the assignment covers only work made for this contract.", "Make sure you keep your pre-existing tools and know-how."],
         "Work Product created specifically for the Client transfers to the Client upon full payment. The Contractor retains pre-existing materials and grants the Client a license to use them as incorporated.",
         "I need to keep my pre-existing tools; can we limit the assignment to project deliverables after payment?",
         [r"(?:hereby\s+)?assigns?\s+(?:to\s+\w+\s+)?(?:all|any|and\s+all)[^.]{0,120}(?:intellectual\s+property|work\s+product|inventions?|rights|copyright)",
          r"work(?:s)?\s+made\s+for\s+hire", r"irrevocably\s+assigns?", r"all\s+(?:right,?\s+title,?\s+and\s+interest)"],
         mitigate=r"(?:retains?|excluding|except\s+for)\s+(?:all\s+)?(?:pre-?existing|background)", mitigated_severity=5),
    Rule("ip_general", "Intellectual Property / License", 3,
         "Describes who owns the intellectual property and what licenses are granted.",
         ["Confirm the scope of any license (exclusive, term, territory)."],
         "Each Party retains ownership of its pre-existing intellectual property; any license is non-exclusive and limited to the purposes of this Agreement.",
         "Please confirm each side keeps its pre-existing IP.",
         [r"intellectual\s+property", r"licen[sc]e\s+(?:to|grant)", r"grants?\s+(?:to\s+\w+\s+)?(?:a|an)\s+(?:\w+\s+){0,3}licen[sc]e"],
         escalate=[(r"(?:perpetual|irrevocable)[^.]{0,60}(?:royalty-?free|worldwide)", 6)]),
    Rule("arbitration", "Binding Arbitration", 5,
         "Disputes go to private arbitration instead of court, usually with limited appeal rights.",
         ["Find out who pays arbitration costs and where it takes place.", "Check for waivers of class actions or jury trial."],
         "Disputes shall first be negotiated for 30 days, then settled by binding arbitration in a mutually agreed location with costs shared equally.",
         "Let's add a negotiation step and split arbitration costs equally.",
         [r"arbitrat", r"\bAAA\b", r"\bJAMS\b"],
         escalate=[(r"(?:sole|exclusive)ly?\s+(?:borne|paid)\s+by|bears?\s+all\s+(?:the\s+)?(?:costs|fees|expenses)|(?:loser|non-prevailing)", 7)]),
    Rule("rights_waiver", "Waiver of Legal Rights", 7,
         "You give up important rights, such as suing in court, a jury trial or joining a class action.",
         ["Check exactly which rights are waived.", "Blanket waivers of future claims may be unenforceable."],
         "A waiver is effective only if in writing and signed, and applies only to the specific right waived.",
         "I'm not comfortable with a blanket waiver; can we limit it to specific enumerated rights?",
         [r"waive[sr]?\b[^.]{0,80}(?:right\s+to\s+(?:sue|a\s+jury|trial|bring|participate)|jury|class\s+action|any\s+(?:and\s+all\s+)?claims?)",
          r"class\s+action\s+waiver", r"jury\s+trial\s+waiver"]),
    Rule("unilateral_change", "Unilateral Changes to Terms", 7,
         "One party can change the contract or prices without your agreement.",
         ["Require written, mutually signed amendments.", "At minimum require advance notice and a right to exit."],
         "No modification of this Agreement is effective unless in a writing signed by both Parties.",
         "Changes to the terms should need both parties' written consent.",
         [r"(?:may|reserves?\s+the\s+right\s+to|can)\s+(?:\w+\s+){0,2}(?:modify|change|amend|update|revise)\b[^.]{0,120}(?:at\s+any\s+time|sole\s+discretion|without\s+(?:prior\s+)?notice|from\s+time\s+to\s+time)"]),
    Rule("liquidated_damages", "Penalties / Liquidated Damages", 5,
         "Fixed sums you must pay if you breach, regardless of the actual loss.",
         ["Check the amounts are a reasonable estimate of loss rather than a penalty."],
         "Liquidated damages shall be a reasonable pre-estimate of loss and shall not exceed the fees paid in the prior 6 months.",
         "Please cap liquidated damages at a reasonable estimate of actual loss.",
         [r"liquidated\s+damages", r"penalt(?:y|ies)\b", r"early\s+termination\s+fee"]),
    Rule("exclusivity", "Exclusivity", 4,
         "Restricts you to working with only this counterparty for some scope or period.",
         ["Check duration and scope.", "Ensure the other side has reciprocal commitments."],
         "Exclusivity applies only to the defined services and territory for the initial term.",
         "Can exclusivity be limited in scope and tied to minimum commitments from your side?",
         [r"(?<!non-)(?<!non\s)\bexclusiv(?:e|ity)\b(?!\s+(?:jurisdiction|venue|remed|of\s+(?:taxes|tax)))"], mitigate=r"non-?\s?exclusive", mitigated_severity=2),
    Rule("late_fees", "Payment Penalties / Late Fees", 4,
         "Extra charges apply if payment is late.",
         ["Check the rate (e.g. 1.5% per month is 18% a year).", "Confirm a grace period exists."],
         "Overdue invoices accrue simple interest at 1% per month after a 10-day grace period.",
         "Please add a grace period and a lower late-payment rate.",
         [r"late\s+(?:fee|charge|payment)", r"interest\s+(?:at|of)\s+(?:the\s+rate|\d)", r"\d+(?:\.\d+)?\s*%\s+per\s+month"]),
    Rule("confidentiality", "Confidentiality", 2,
         "Protects sensitive information shared between the parties.",
         ["Check the definition is not overly broad.", "Ensure standard exceptions exist (public info, legal disclosure)."],
         "Each Party shall protect Confidential Information for 3 years; public, independently developed, or legally compelled information is excluded.",
         "Please add standard carve-outs and a fixed term.",
         [r"confidential"],
         escalate=[(r"in\s+perpetuity|perpetual|indefinite|under\s+no\s+circumstances|even\s+(?:if|when)\s+(?:required|compelled)", 6),
                   (r"(?:only|solely)\s+(?:the\s+)?(?:receiving|recipient)", 4)]),
    Rule("governing_law", "Governing Law & Venue", 2,
         "Which law applies and where disputes must be filed.",
         ["Check the venue is not remote or costly for you."],
         "This Agreement is governed by the laws of [Your State]; proceedings shall be brought in courts located in [Your County].",
         "Can we use a neutral or mutually convenient jurisdiction?",
         [r"governed\s+by\s+(?:and\s+construed\s+(?:in\s+accordance\s+)?with\s+)?the\s+laws", r"governing\s+law", r"exclusive\s+(?:jurisdiction|venue)", r"\bvenue\b"]),
    Rule("force_majeure", "Force Majeure", 2,
         "Excuses a party from performing when extraordinary events occur.",
         ["Confirm it applies to both parties and does not excuse payment."],
         "Neither Party is liable for delay caused by events beyond its reasonable control, and shall resume performance promptly.",
         "Make sure force majeure is mutual.",
         [r"force\s+majeure", r"acts?\s+of\s+god"]),
]
RULES_BY_KEY = {r.key: r for r in RULES}


def _sentence_around(text: str, start: int, end: int) -> str:
    """The sentence containing the match; if it is just a heading, include the following sentence."""
    s = max(text.rfind(". ", 0, start), text.rfind("\n", 0, start))
    s = 0 if s < 0 else s + 1

    def next_end(pos):
        c = [i for i in (text.find(". ", pos), text.find("\n", pos)) if i >= 0]
        return min(c) + 1 if c else len(text)

    e = next_end(end)
    if e - s < 140 and e < len(text):
        e = next_end(e + 1)
    return text[s:e].strip()


def detect(text: str) -> list[dict]:
    """Return rule hits for a chunk: [{rule, severity, evidence}] with supersedes applied."""
    hits = {}
    for r in RULES:
        m = next((m for m in (p.search(text) for p in r.patterns) if m), None)
        if not m:
            continue
        sev = r.severity
        for rx, s in r.escalate:
            if rx.search(text):
                sev = max(sev, s)
        if r.mitigate and r.mitigate.search(text) and sev >= r.mitigated_severity:
            sev = r.mitigated_severity
        hits[r.key] = {"rule": r, "severity": sev, "evidence": _sentence_around(text, m.start(), m.end())}
    for h in list(hits.values()):
        for k in h["rule"].supersedes:
            hits.pop(k, None)
    return list(hits.values())
