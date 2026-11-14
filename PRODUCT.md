# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Christopher Virrueta (Chris), the author of the model, is the primary and practically only daily user. He is a 19-year-old Economics student in Morelia, México, learning data science. He opens the page on his phone shortly before NBA games to decide which bets are worth considering, comparing the model's numbers against the odds he sees at a Mexican sportsbook (Caliente). Recruiters or reviewers may see the page through the GitHub portfolio, but they are a secondary audience and are not who the interface is designed for.

## Product Purpose

A personal dashboard for an NBA probability model. Each day it shows upcoming games with the model's probability for the winner, spread and total, the market's fair probability (Pinnacle without margin), the best available odds, the expected value, a suggested stake, and a flag when the model disagrees with the market too much to be trusted. It also keeps a log of simulated (paper-trading) bets with results, ROI and CLV, plus the current Elo ranking and a short guide.

Success means Chris can decide in under a minute, on his phone, whether any bet today is worth it and how much to stake, and can tell over the weeks whether the model has a real edge (positive CLV). Right now all bets are simulated; no real money until the evidence supports it.

## Positioning

It is Chris's own model, validated out of sample, and it is deliberately honest: it labels suspicious edges instead of hyping them, measures itself against the closing line, and states that markets are hard to beat. It is not a tipster service and never promises profit.

## Operating Context

- Mobile first: used on a phone, quickly, right before games (evening, Mexico City time).
- Odds in American format. Real betting happens at Caliente, which is not in the data feed, so the page includes a calculator where Chris types the Caliente price to get EV and stake.
- Data is regenerated once a day by `rutina.bat` on his Windows PC and published to GitHub Pages; the page itself is a static file that reads `datos.json`.
- Interface language: Spanish (México).

## Capabilities and Constraints

- Stack: static HTML/CSS/JS in one file (`web/index.html`), no framework, no build step; data in `web/datos.json`; hosted on GitHub Pages via a GitHub Actions workflow.
- Markets: moneyline (winner), spread and total. Per game: projection (margin and total), injuries of rotation players with probability of playing, best price and book, EV, state (value / suspicious / none), suggested stake.
- Simulated bankroll (default $1,000), quarter Kelly, 2% cap per bet, EV thresholds of 3% (winner) and 5% (spreads/totals).
- Sections: Hoy (games), Apuestas (KPIs and log), Ranking (Elo), Guía (how to read it).
- Terminology in use: momio, EV, CLV, spread, total/over/under, push, Pinnacle, Kelly, Elo, "Valor", "Sospechosa", "Bitácora".

## Brand Commitments

Name: "NBA · Probabilidades". No logo or other brand assets. Must not use NBA team logos, league marks or player photos.

## Evidence on Hand

Real model outputs only: `web/datos.json` (games, odds, probabilities, injuries, bet log), validation results in `README.md` and charts in `docs/img/`. No testimonials, users or track record exist yet; the bet log has only a few days of simulated bets. Never fabricate performance, win rates or profits.

## Product Principles

1. Decision first: the answer to "is anything worth betting today, and how much?" must be obvious at a glance.
2. Honesty over excitement: suspicious edges, uncertainty and simulated status are always visible; nothing reads like a guaranteed win.
3. Model versus market, always side by side: every model number is shown next to what the market says.
4. Fast on a phone in one hand: thumb-reachable navigation, no horizontal scrolling for key info, readable at a glance.
5. Measure, don't hope: CLV and the log are first-class, because they tell whether the model works.

## Accessibility & Inclusion

No product-specific requirement established beyond readable contrast and touch targets on mobile. Color must never be the only carrier of state (value / suspicious / win / loss also need text).
