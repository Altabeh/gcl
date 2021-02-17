
"""
Regex patterns used in the GCLParse class 
go in here.
"""

class GCLRegex:
    case_patterns = [(r"/scholar_case\?(?:.*?)=(\d+)", r"\g<1>")]
    casenumber_patterns = [(r"scidkt=(.*?)&", "")]
    just_number_patterns = [(r"^\d+$", "")]
    docket_number_patterns = [
        (
            r"((?:(?<=,)|(?<=^))(?: +)?Nos?[., ]+(?:\b| +)((?:[\w:\-. ]|\([A-Za-z/]+\))+)+)",
            "",
        )
    ]
    docket_number_comp_patterns = [
        (r"((?:(?<=,)|(?<=^)|(?<=No\.)|(?<=Nos\.))(?: +)(\d+[:-][A-Z\d+\-\/ ]+))", "")
    ]
    docket_appeals_patterns = [(r"(?:\d{2,4}|(?<=, )|(?<=, and)(?: +)?)-\d{1,5}", "")]
    docket_us_patterns = [(r"\d+(?:-\d+)?", "")]
    docket_clean_patterns = r"(?:(?<=^)|(?<=,))(?: +)?(?:(?:C\.?A|D(?:[oc]+)?ke?ts?|MDL| +|Case|Crim|Civ)+(?:il|inal)?(?:(?:Action|CV|A|[. ])+)?)?((?:C\.A|Nos?)\.:?)(?: )?"
    patent_number_pattern = r"(?:(?:RE|PP|D|AI|X|H|T)? ?\d{1,2}[,./]\-?)?(?:(?:RE|PP|D|AI|X|H|T) ?\d{2,3}|\d{3})[,./]\-?\d{3}(?: ?AI)?\b"
    patent_reference_patterns = r'["`\'#’]+(\d{3,4}) ?(?:[Aa]pplication|[Pp]atent)\b|(?:[Aa]pplication|[Pp]atent)\b +["`\'#’]+(\d{3,4})'
    claim_patterns_1 = (
        r"[Cc]laims?([\d\-, and]+)(?:[\w ]+)(?:(?:[\(\"“ ]+)?(?: ?the ?)?[#`\'’]+(\d+))"
    )
    claim_patterns_2 = r"(?<=[cC]laim[s ])(?:([\d,\- ]+)(?:(?:[, ]+)?and ([\d\- ]+))*)+"
    patent_number_patterns_1 = [(r" " + patent_number_pattern, "")]
    patent_number_patterns_2 = [(r"[USnitedpPaNso. ]+" + patent_number_pattern, "")]
    judge_patterns = [
        (
            r"^(m[rs]s?\.? )?C[Hh][Ii][Ee][Ff] J[Uu][Dd][Gg][Ee][Ss]? |^(m[rs]s?\.? )?(?:C[Hh][Ii][Ee][Ff] )?J[Uu][Ss][Tt][Ii][Cc][Ee][Ss]? |^P[rR][Ee][Ss][Ee][nN][T]: |^B[eE][fF][oO][rR][Ee]: | J[Uu][Dd][Gg][Ee][Ss]?[:.]?$|, [UJSC. ]+:?$|, (?:[USD. ]+)?[J. ]+:?$|, J[Uu][Ss][Tt][Ii][Cc][Ee][Ss]?\.?$",
            "",
        )
    ]
    judge_dissent_concur_patterns = r"(?<=\$)([^\$][\w\W][^\$]+((?:[Cc]oncurring|[Dd]issenting)[a-z.:;,\- ]+))(?=\$)"
    judge_clean_patterns_1 = [
        (
            r", joined$| ?—$|^Opinion of the Court by |, United States District Court| ?Pending before the Court are:?| ?Opinion for the court filed by[\w\'., ]+| delivered the opinion of the Court\.|^Appeal from ",
            "",
        )
    ]
    judge_clean_patterns_2 = [
        (
            r"^(?:the )?hon\. |^(?:the )?honorable |^before:? |^present:? |^m[rs]s?\.? |, (?:u\.?\s\.?)?d?\.?j\.\.?$|, j\.s\.c\.$",
            "",
        )
    ]
    judge_clean_patterns_3 = [
        (
            r"senior|chief|u\.?s\.?|united states|circuit|district|magistrate|chief|court|judges?",
            "",
        )
    ]
    date_patterns = [
        (
            r"((?:January|February|March|April|May|June|July|August|September|October|November|December)(?:[0-9, ]+))",
            "",
        )
    ]
    short_month_date_patterns = [
        (
            r"((?:(Jan|Feb|Mar|Apr|May|June?|July?|Aug|Sept?|Oct|Nov|Dec)\.?(?: +)?(?:([0-9]{1,2})\b,?)?(?: +)?)?(\d{4}))",
            "",
        ),
    ]
    long_bluebook_patterns = [
        (r"(?:^in re:?| +v\.? +).*(?:en banc|ed\.|cir\.|\d{4})\)$", "")
    ]
    extras_citation_patterns = [
        (
            r",(?:(?:[\d& ,\-\*]+)|(?:[nat&\- \*\d]+(?:[\. ]+(?:(?:(?:[\.\- ]+)?\d+)?)+ ?)?))(?= \(|,)",
            "",
        ),
        (
            r"((?:^in re:?|(?:.)* v\.? +).*(?:\(en banc|ed\.|Cir\.|\d{4})\))(?:(?:(?: +)?\(.*?\))+)?$",
            r"\g<1>",
        ),
        (
            r"^(?:[\w\'\-\.]+)?\"(?: +)?| +\(\".*?\"\)|\b at ?\*?(?: +)?(?:\d+(?: ?\- ?\d+)?)+",
            "",
        ),
        (r"Fed\. ?Appx\.", "F. App'x"),
        (r"F\. ?Supp\. ?(\d+)d", r"F. Supp. \g<1>d"),
        (r"L\. ?Ed\. ?(\d+)d", r"L. Ed. \g<1>d"),
        (r"S\.Ct\.", "S. Ct."),
    ]
    federal_court_patterns = [(r"( ?([,-]) ([\w:. \']+) (\d{4}))$", "")]
    state_court_patterns = [(r"( ?([-,]) ([\w. ]+): (.*?) (\d{4}))$", "")]
    approx_court_location_patterns = [
        (r"(\([\w\.,\' ]+\))(?: +)?(?:\(en banc\))?$", "")
    ]
    court_clean_patterns = [
        (r"Cir\.(\d+)", r"Cir. \g<1>"),
        (r"Fed\.Cir\.", "Fed. Cir."),
        (r"CCPA", "C.C.P.A."),
        (r"PTAB", "P.T.A.B."),
        (r"Dept", "Dep't"),
        (r"([\(| ])(Fed|Cir)(?!\.)\b", r"\g<1>\g<2>."),
        (r"(?<! |\()(\d{4}\))(?: +)?(\(?:en banc\))?$", r" \g<1>"),
        (r"(?<=\.)([A-Z][a-z\']+\.)", r" \g<1>"),
    ]
    reporter_empty_patterns = r"(?:(?:[\-—–_\d ]+))(?:X)(?:(?: +)(?:[\-—–_]+)[, ]+)+"
    reporter_patterns = r"((\d+)(?: +)?(X)(?: +)?([\d\-—–_ ]+)([at,\.\d\-—–_\*¶ ]+)?([n\.\d\-—–_\*¶ ]+)?)"
    special_chars_patterns = [(r"\W", "")]
    strip_patterns = [(r"\n", " "), (r" +", " ")]
    extra_char_patterns = [(r"^[,. ]+|[,. ]+$", "")]
    comma_space_patterns = [(r"^[, ]+|[, ]+$", "")]
    space_patterns = [(r"^ +| +$", "")]
    boundary_patterns = [(r"^(?:[Tt]he |[.,;:\"\'\[\(\- ])+|[;:\"\'\)\]\- ]+$|'s$", "")]
    end_sentence_patterns = [
        (
            r"(?:AFFIRMED|ORDERED|REMANDED|DENIED|REVERSED|GRANTED|[pP][aA][rR][tT]|@@@@\[[\d\*]+\]|[.!?])[\"\'”’]?$",
            "",
        )
    ]
    roman_patterns = [(r"^[MDCLXVI](?:M|D|C{0,4}|L|X{0,4}|V|I{0,4})$", "")]
    abbreviation_patterns = [(r"^[JS][Rr]\.$", "")]
    page_patterns = [(r"(?: +)?\+page\[\d+\]\+ +", " ")]
    clean_footnote_patterns = [(r" ?@@@@\[[\d\*]+\] ?", " ")]