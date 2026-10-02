# Which project a subnet number stands for

A netuid is reused. When a subnet is deregistered, the next registration gets its number, and
a team can hand a running subnet to another team that renames it. A post that says "SN900"
can therefore mean a project that held the number earlier, even if the post was written
after the current project started. And a digit after the word "subnet" is sometimes no
subnet number at all.

The clear cases are removed by script: a post that names a subnet by its number alone and
was written before the day on which the current project started does not count
(`snprice.textmatch.valid_for_project`). What is left is read by two independent readers.

## What is read

Every pair of a post and a subnet that was matched by the number alone (rule `id` in
`data/evidence/kol_mentions_wave<N>.csv`). Pairs matched through a name or handle of the
current project are not read: they name it.

## Material

For each case the reader gets:

- the post's text and the day it was posted,
- the netuid and the name of the project that holds it now,
- the day the current project started, and the day of the netuid's current registration,
- every name that was ever set on the netuid, with the day it was set.

Names set before the day the current project started belong to earlier projects. Names set
on or after that day are names the current project has used; they count as the current
project.

Readers use nothing else: no web, no prices, no knowledge of their own about the projects.

## Question

Does the number in this post stand for the project that holds the netuid now?

Answer `no` only if the text shows it, in one of three ways:

1. The post attaches the number to another project: a name or handle that is not the
   current project's. A misspelling or a short form of the current name is the current
   project.
2. The post speaks of the subnet with that number as something that existed or ended
   before the current project started: it failed, was deregistered, was sold, or the events
   described are dated before the start.
3. The digits are not a subnet number: part of an address, a price, a count.

Answer `yes` in every other case, also when the post gives no hint either way. The date
rule then stands.

Examples, with an invented subnet: Acme holds netuid 900 since 1 July 2026; before that the
netuid carried the name Bolt.

| Post (written in August 2026) | Answer |
|---|---|
| "SN900 just shipped its first product" | yes |
| "Subnet 900: [link]" | yes |
| "Acmee (SN900) is growing fast" | yes: a misspelling of the current name |
| "Remember Bolt (SN900)? Gone." | no: the number is attached to an earlier name |
| "He ran SN900 last year and it failed" | no: a subnet that ended before the current project started |
| "A new subnet registered and took the place of Bolt SN900" | no: the number is attached to the earlier project, although the news is about the new one |
| "send it to my subnet 5Gx..." followed by a wallet address | no: not a subnet number |

## Answer format

One answer per case: `yes` or `no`. Every `no` comes with one short reason in the reader's
own words. Reasons do not quote the post: post texts are not republished, and a reason that
repeats six or more words in a row from the post is refused when the answers are collected.

## Use

A pair is dropped only if both readers answer `no` (`snprice.kol.stands_for_current`). If
they differ, the pair counts. Dropped pairs stay in `data/evidence/kol_coding_wave<N>.csv`
with `counts = 0`, next to both answers.
