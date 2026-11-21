"""Extend the 6-filing starter corpus to the 15 filings x 5 companies in the brief.

The kit ships ACMR/FINC/ZYNT for FY2022-2023 only. This script adds
  * ACMR/FINC/ZYNT FY2021 (same template, slight year-on-year differences), and
  * two new synthetic companies, QRTX (payments) and HLXR (health analytics), FY2021-2023.
Existing files are never overwritten unless --force is passed.
"""
import argparse, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "corpus", "filings")

BASE_BUSINESS = ("{t} operates in the enterprise software market with two segments: Cloud Services and "
                 "On-Premise Licenses. Key markets include APAC and North America. Revenue grew due to new "
                 "subscriptions and partner channels.")
BOILER_LEGAL = ("We are subject to routine litigation. No proceedings are expected to have a material "
                "adverse effect.")


def fin(rev, gm, rd):
    return f"Total revenue: ${rev}M. Gross margin: {gm}%. R&D as % of revenue: {rd}%."


# (intended_topic, bullet) -- intended topics are used by tests to check the topic detector.
def sw_2021(t):
    return dict(
        business=BASE_BUSINESS.format(t=t),
        risks=[("cybersecurity", "Cybersecurity incidents and data breaches could disrupt operations and lead to regulatory penalties."),
               ("supply_chain", "Supply chain concentration and single-source vendors may cause fulfillment delays."),
               ("privacy_regulation", "Regulatory changes in privacy (GDPR/CCPA) and financial reporting could increase compliance costs."),
               ("customer_sla", "Customer churn risk if service-level agreements are not met."),
               ("competition", "Intense competition and pricing pressure from larger platform vendors could reduce market share.")],
        mdna=("Management discusses year-over-year revenue growth, gross margin trends, and opex discipline. "
              "Notable trends include migration of customers to cloud subscriptions."),
        legal=BOILER_LEGAL)


FILINGS = {
    "ACMR_2021": {**sw_2021("ACMR"), "fin": fin(480, 62, 21)},
    "FINC_2021": {**sw_2021("FINC"), "fin": fin(805, 64, 16)},
    "ZYNT_2021": {**sw_2021("ZYNT"), "fin": fin(355, 72, 12)},
}

QR_BUS = ("QRTX operates a digital payments platform with two segments: Merchant Processing and Consumer Wallet. "
          "Key markets include Europe and Latin America. Revenue grew due to higher transaction volumes and new "
          "merchant onboarding.")
QR_R = {
    "fraud": ("cybersecurity", "Payment fraud and cybersecurity incidents could result in financial losses, data breaches, and loss of merchant trust."),
    "aml": ("regulatory_compliance", "Failure to maintain payment licenses and comply with anti-money laundering rules could trigger regulatory penalties."),
    "conc": ("customer_concentration", "A significant portion of our revenue comes from a small number of large merchants."),
    "interchange": ("competition", "Interchange fee caps and pricing pressure from competing processors could compress take rates."),
    "rates": ("interest_rate", "Rising interest rates may increase funding costs for settlement float."),
    "fx": ("fx", "Foreign exchange volatility across euro and Latin American currencies could reduce reported revenue."),
    "talent": ("talent", "Retaining engineering talent in a competitive labor market may become more difficult."),
}
FILINGS["QRTX_2021"] = dict(business=QR_BUS, risks=[QR_R[k] for k in ("fraud", "aml", "conc", "interchange")],
    mdna="Management discusses transaction volume growth, take-rate trends, and operating leverage. Notable trends include expansion of merchant onboarding in Brazil.",
    legal=BOILER_LEGAL, fin=fin(310, 48, 11))
FILINGS["QRTX_2022"] = dict(business=QR_BUS, risks=[QR_R[k] for k in ("fraud", "aml", "conc", "interchange", "rates", "fx")],
    mdna="Management discusses transaction volume growth, take-rate trends, and operating leverage. Notable trends include higher cross-border volumes and rising funding costs.",
    legal=BOILER_LEGAL, fin=fin(402, 49, 12))
FILINGS["QRTX_2023"] = dict(business=QR_BUS, risks=[QR_R[k] for k in ("fraud", "aml", "conc", "interchange", "rates", "fx", "talent")][:6],
    mdna="Management discusses transaction volume growth, take-rate trends, and operating leverage. Notable trends include stabilizing take rates and investments in fraud-detection models.",
    legal=("A regulator in one European market opened an inquiry into our anti-money laundering controls, and we are "
           "cooperating fully. We cannot predict the outcome. Other proceedings are routine."),
    fin=fin(515, 51, 13))

HL_BUS = ("HLXR provides healthcare analytics software with two segments: Provider Analytics and Payer Solutions. "
          "Key markets include the United States and Canada. Revenue grew due to new hospital system contracts and "
          "expanded payer analytics modules.")
HL_R = {
    "phi": ("cybersecurity", "Unauthorized access to protected health information could result in data breaches, regulatory penalties, and reputational harm."),
    "hipaa": ("privacy_regulation", "Changes to HIPAA and other health data privacy rules could increase compliance costs."),
    "conc": ("customer_concentration", "Hospital systems account for a significant portion of revenue, and the loss of a major customer could harm results."),
    "talent": ("talent", "Attrition of data scientists and engineers could slow product development."),
    "patent": ("litigation", "A competitor has asserted that certain features infringe its patents, and defending such claims could be costly."),
    "reimb": ("regulatory_compliance", "Changes in healthcare reimbursement policy could reduce customer budgets for analytics."),
}
FILINGS["HLXR_2021"] = dict(business=HL_BUS, risks=[HL_R[k] for k in ("phi", "hipaa", "conc", "talent")],
    mdna="Management discusses contract bookings, net revenue retention, and opex discipline. Notable trends include expansion within existing hospital systems.",
    legal=BOILER_LEGAL, fin=fin(205, 71, 22))
FILINGS["HLXR_2022"] = dict(business=HL_BUS, risks=[HL_R[k] for k in ("phi", "hipaa", "conc", "talent", "patent")],
    mdna="Management discusses contract bookings, net revenue retention, and opex discipline. Notable trends include longer sales cycles at large health systems.",
    legal=("In 2022 a competitor filed a patent infringement complaint against us. We believe the claims are without "
           "merit and intend to defend vigorously, but an adverse outcome could be material."),
    fin=fin(248, 72, 23))
FILINGS["HLXR_2023"] = dict(business=HL_BUS, risks=[HL_R[k] for k in ("phi", "hipaa", "conc", "patent", "reimb")],
    mdna="Management discusses contract bookings, net revenue retention, and opex discipline. Notable trends include higher payer analytics adoption and investments in clinical AI models.",
    legal=("The patent infringement matter filed in 2022 remains pending and discovery is ongoing. We cannot estimate "
           "any possible loss. Other proceedings are routine."),
    fin=fin(301, 73, 24))


def render(fid, d):
    t, y = fid.split("_")
    risks = "\n".join(f"- {b}" for _, b in d["risks"])
    return (f"# {t} {y} Annual Filing (Synthetic)\n\n## Business\n{d['business']}\n\n## Risk Factors\n{risks}\n\n"
            f"## MD&A\n{d['mdna']}\n\n## Legal Proceedings\n{d['legal']}\n\n## Financials\n{d['fin']}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="overwrite existing files")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    for fid, d in sorted(FILINGS.items()):
        p = os.path.join(OUT, f"{fid}.md")
        if os.path.exists(p) and not a.force:
            print(f"skip   {fid} (exists)")
            continue
        open(p, "w", encoding="utf-8").write(render(fid, d))
        print(f"wrote  {fid}")


if __name__ == "__main__":
    main()
