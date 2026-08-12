# Part 2 — withheld

These deductive workbooks must NOT be sent to a coder until that coder's
Part 1 emergent workbook has been returned and passes its structural check.
Seeing the codebook cannot be undone, so the sequence is enforced rather
than trusted.

Place the returned Part 1 workbook in `../gold_standard_returned/`, then:

    py scripts/build_gold_standard_package.py --release-part2 A
    py scripts/build_gold_standard_package.py --release-part2 B

Release refuses unless the returned workbook has no added, deleted,
duplicated or reordered rows and records at least one theme per unit.
