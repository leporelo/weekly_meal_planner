"""Website publisher that generates static HTML pages for the meal plan.

Generates a mobile-friendly static website into docs/ and commits/pushes
to the main branch for GitHub Pages serving.
"""

import logging
import os
import subprocess
from datetime import date, timedelta
from pathlib import Path

from src.models import GroceryList, MealPlan, Recipe, UserProfile

logger = logging.getLogger(__name__)

# --- CSS Styles ---

EMBEDDED_CSS = """
:root {
    --green-dark: #2d5016;
    --green-mid: #4a7c23;
    --green-light: #6ba33e;
    --cream: #faf8f0;
    --white: #ffffff;
    --gray-light: #f5f5f5;
    --gray-mid: #666666;
    --gray-dark: #333333;
    --shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
    --shadow-hover: 0 4px 16px rgba(0, 0, 0, 0.12);
    --radius: 12px;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen,
        Ubuntu, Cantarell, sans-serif;
    background-color: var(--cream);
    color: var(--gray-dark);
    line-height: 1.6;
    padding: 0;
}

header {
    background: linear-gradient(135deg, var(--green-dark), var(--green-mid));
    color: var(--white);
    padding: 2rem 1.5rem;
    text-align: center;
}

header h1 {
    font-size: 1.8rem;
    margin-bottom: 0.3rem;
    font-weight: 700;
}

header .date-range {
    font-size: 1.1rem;
    opacity: 0.9;
}

nav.day-nav {
    background: var(--white);
    padding: 1rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    justify-content: center;
    border-bottom: 1px solid #e0e0e0;
    position: sticky;
    top: 0;
    z-index: 100;
}

nav.day-nav a {
    color: var(--green-dark);
    text-decoration: none;
    padding: 0.4rem 0.8rem;
    border-radius: 6px;
    font-size: 0.9rem;
    font-weight: 500;
    transition: background 0.2s;
}

nav.day-nav a:hover {
    background: var(--gray-light);
}

main {
    max-width: 900px;
    margin: 0 auto;
    padding: 1.5rem;
}

.day-section {
    margin-bottom: 2.5rem;
}

.day-section h2 {
    color: var(--green-dark);
    font-size: 1.5rem;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid var(--green-light);
}

.meal-label {
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--green-mid);
    margin-bottom: 0.4rem;
}

.recipe-card {
    background: var(--white);
    border-radius: var(--radius);
    padding: 1.2rem;
    margin-bottom: 1rem;
    box-shadow: var(--shadow);
    transition: box-shadow 0.2s;
}

.recipe-card:hover {
    box-shadow: var(--shadow-hover);
}

.recipe-card h3 {
    font-size: 1.1rem;
    color: var(--gray-dark);
    margin-bottom: 0.5rem;
}

.recipe-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    font-size: 0.85rem;
    color: var(--gray-mid);
    margin-bottom: 0.7rem;
}

.recipe-meta span {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
}

.servings-list {
    font-size: 0.9rem;
    margin-bottom: 0.8rem;
    padding: 0.5rem 0.8rem;
    background: var(--gray-light);
    border-radius: 6px;
}

.servings-list .person {
    display: inline-block;
    margin-right: 1rem;
}

.servings-list .person strong {
    color: var(--green-dark);
}

details {
    margin-top: 0.5rem;
}

details summary {
    cursor: pointer;
    font-weight: 500;
    font-size: 0.9rem;
    color: var(--green-mid);
    padding: 0.3rem 0;
    user-select: none;
}

details summary:hover {
    color: var(--green-dark);
}

details .content {
    padding: 0.8rem 0;
    font-size: 0.9rem;
}

details .content ul {
    list-style: none;
    padding: 0;
}

details .content ul li {
    padding: 0.2rem 0;
    padding-left: 1rem;
    position: relative;
}

details .content ul li::before {
    content: "•";
    position: absolute;
    left: 0;
    color: var(--green-light);
}

details .content .instructions {
    white-space: pre-line;
    line-height: 1.7;
}

.grocery-section {
    margin-top: 3rem;
    padding-top: 2rem;
    border-top: 2px solid var(--green-light);
}

.grocery-section h2 {
    color: var(--green-dark);
    font-size: 1.5rem;
    margin-bottom: 1.5rem;
}

.grocery-category {
    margin-bottom: 1.5rem;
}

.grocery-category h3 {
    font-size: 1rem;
    font-weight: 600;
    color: var(--green-mid);
    margin-bottom: 0.5rem;
    text-transform: capitalize;
}

.grocery-category ul {
    list-style: none;
    padding: 0;
}

.grocery-category ul li {
    padding: 0.25rem 0 0.25rem 1rem;
    position: relative;
    font-size: 0.9rem;
}

.grocery-category ul li::before {
    content: "▪";
    position: absolute;
    left: 0;
    color: var(--green-light);
}

.archive-link {
    text-align: center;
    margin-top: 2rem;
    padding: 1rem;
}

.archive-link a {
    color: var(--green-dark);
    font-weight: 500;
    text-decoration: none;
    border-bottom: 1px solid var(--green-light);
    padding-bottom: 2px;
}

.archive-link a:hover {
    color: var(--green-mid);
}

footer {
    text-align: center;
    padding: 2rem 1rem;
    font-size: 0.8rem;
    color: var(--gray-mid);
}

/* Archive page */
.archive-list {
    list-style: none;
    padding: 0;
}

.archive-list li {
    margin-bottom: 0.8rem;
}

.archive-list a {
    display: block;
    background: var(--white);
    padding: 1rem 1.2rem;
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    color: var(--green-dark);
    text-decoration: none;
    font-weight: 500;
    transition: box-shadow 0.2s, transform 0.2s;
}

.archive-list a:hover {
    box-shadow: var(--shadow-hover);
    transform: translateY(-1px);
}

/* Mobile responsive */
@media (max-width: 600px) {
    header {
        padding: 1.5rem 1rem;
    }

    header h1 {
        font-size: 1.4rem;
    }

    main {
        padding: 1rem;
    }

    .recipe-meta {
        flex-direction: column;
        gap: 0.3rem;
    }

    nav.day-nav {
        padding: 0.7rem;
        gap: 0.3rem;
    }

    nav.day-nav a {
        font-size: 0.8rem;
        padding: 0.3rem 0.6rem;
    }
}
"""


class WebsitePublisher:
    """Generates static HTML pages from a meal plan and pushes to GitHub Pages."""

    def __init__(self, repo_path: Path, remote_url: str = "origin") -> None:
        """Initialize with the local repo path.

        Args:
            repo_path: Path to the local git repository root.
            remote_url: Git remote name for pushing (default: "origin").
        """
        self.repo_path = repo_path
        self.remote_url = remote_url
        self.docs_path = repo_path / "docs"

    def publish(
        self,
        meal_plan: MealPlan,
        profiles: list[UserProfile],
        grocery_list: GroceryList,
    ) -> bool:
        """Generate HTML and commit/push to main branch.

        Args:
            meal_plan: The weekly meal plan to publish.
            profiles: User profiles (for per-person serving calculations).
            grocery_list: The consolidated grocery list.

        Returns:
            True if publish succeeded, False otherwise.
        """
        try:
            monday = self._get_monday_date()
            week_key = monday.isoformat()

            # Generate all HTML pages
            self._generate_index(meal_plan, profiles, grocery_list, monday)
            self._generate_week_page(meal_plan, profiles, grocery_list, monday)
            self._generate_archive()

            # Git commit and push
            return self._git_commit_and_push(week_key)

        except Exception as e:
            logger.error("Website publish failed: %s", e)
            return False

    def _get_monday_date(self) -> date:
        """Get the Monday date of the current week."""
        today = date.today()
        # Monday is weekday 0
        days_since_monday = today.weekday()
        return today - timedelta(days=days_since_monday)

    def _generate_index(
        self,
        meal_plan: MealPlan,
        profiles: list[UserProfile],
        grocery_list: GroceryList,
        monday: date,
    ) -> None:
        """Generate docs/index.html with the current week's plan."""
        sunday = monday + timedelta(days=6)
        date_range = f"{monday.strftime('%B %d')} – {sunday.strftime('%B %d, %Y')}"

        body_html = self._render_meal_plan_body(
            meal_plan, profiles, grocery_list, date_range, is_archive=False
        )

        html = self._wrap_html(
            title=f"Vegan Meal Plan – {date_range}",
            body=body_html,
        )

        self.docs_path.mkdir(parents=True, exist_ok=True)
        (self.docs_path / "index.html").write_text(html, encoding="utf-8")
        logger.info("Generated docs/index.html")

    def _generate_week_page(
        self,
        meal_plan: MealPlan,
        profiles: list[UserProfile],
        grocery_list: GroceryList,
        monday: date,
    ) -> None:
        """Generate docs/weeks/YYYY-MM-DD/index.html for the given week."""
        sunday = monday + timedelta(days=6)
        date_range = f"{monday.strftime('%B %d')} – {sunday.strftime('%B %d, %Y')}"
        week_key = monday.isoformat()

        body_html = self._render_meal_plan_body(
            meal_plan, profiles, grocery_list, date_range, is_archive=True
        )

        html = self._wrap_html(
            title=f"Vegan Meal Plan – {date_range}",
            body=body_html,
        )

        week_dir = self.docs_path / "weeks" / week_key
        week_dir.mkdir(parents=True, exist_ok=True)
        (week_dir / "index.html").write_text(html, encoding="utf-8")
        logger.info("Generated docs/weeks/%s/index.html", week_key)

    def _generate_archive(self) -> None:
        """Generate docs/archive.html listing all past weeks."""
        weeks_dir = self.docs_path / "weeks"
        week_folders: list[str] = []

        if weeks_dir.exists():
            for entry in sorted(weeks_dir.iterdir(), reverse=True):
                if entry.is_dir() and (entry / "index.html").exists():
                    week_folders.append(entry.name)

        # Build archive body
        lines: list[str] = []
        lines.append('<header>')
        lines.append('  <h1>🌱 Meal Plan Archive</h1>')
        lines.append('  <div class="date-range">All past weekly plans</div>')
        lines.append('</header>')
        lines.append('<main>')

        if week_folders:
            lines.append('<ul class="archive-list">')
            for week_key in week_folders:
                try:
                    monday = date.fromisoformat(week_key)
                    sunday = monday + timedelta(days=6)
                    label = f"{monday.strftime('%B %d')} – {sunday.strftime('%B %d, %Y')}"
                except ValueError:
                    label = week_key
                lines.append(
                    f'  <li><a href="weeks/{week_key}/index.html">Week of {label}</a></li>'
                )
            lines.append('</ul>')
        else:
            lines.append('<p>No archived weeks yet.</p>')

        lines.append('<div class="archive-link"><a href="index.html">← Current Week</a></div>')
        lines.append('</main>')
        lines.append('<footer>Generated by Vegan Meal Planner</footer>')

        html = self._wrap_html(
            title="Meal Plan Archive",
            body="\n".join(lines),
        )

        (self.docs_path / "archive.html").write_text(html, encoding="utf-8")
        logger.info("Generated docs/archive.html")

    def _render_meal_plan_body(
        self,
        meal_plan: MealPlan,
        profiles: list[UserProfile],
        grocery_list: GroceryList,
        date_range: str,
        is_archive: bool,
    ) -> str:
        """Render the full meal plan page body HTML.

        Args:
            meal_plan: The meal plan to render.
            profiles: User profiles for per-person servings.
            grocery_list: The grocery list to include.
            date_range: Formatted date range string.
            is_archive: If True, adjust nav links for archive location.

        Returns:
            HTML string for the page body.
        """
        max_target = max(p.protein_target_g for p in profiles)
        lines: list[str] = []

        # Header
        lines.append('<header>')
        lines.append('  <h1>🌱 Weekly Vegan Meal Plan</h1>')
        lines.append(f'  <div class="date-range">{_escape(date_range)}</div>')
        lines.append('</header>')

        # Day navigation
        lines.append('<nav class="day-nav">')
        for day_data in meal_plan.days:
            day_name = day_data.get("day", "Unknown")
            anchor = day_name.lower().replace(" ", "-")
            lines.append(f'  <a href="#{anchor}">{_escape(day_name[:3])}</a>')
        lines.append('</nav>')

        # Main content
        lines.append('<main>')

        # Day sections
        for day_data in meal_plan.days:
            day_name = day_data.get("day", "Unknown")
            anchor = day_name.lower().replace(" ", "-")
            lines.append(f'<section class="day-section" id="{anchor}">')
            lines.append(f'  <h2>{_escape(day_name)}</h2>')

            # Meals
            for meal_slot in ("breakfast", "lunch", "dinner"):
                recipe = day_data.get(meal_slot)
                if isinstance(recipe, Recipe):
                    lines.append(f'  <div class="meal-label">{meal_slot}</div>')
                    lines.append(
                        self._render_recipe_card(recipe, profiles, max_target)
                    )

            # Snacks
            snacks = day_data.get("snacks")
            if isinstance(snacks, list):
                for i, snack in enumerate(snacks):
                    if isinstance(snack, Recipe):
                        label = f"Snack {i + 1}" if len(snacks) > 1 else "Snack"
                        lines.append(f'  <div class="meal-label">{label}</div>')
                        lines.append(
                            self._render_recipe_card(snack, profiles, max_target)
                        )

            lines.append('</section>')

        # Grocery list
        lines.append('<section class="grocery-section">')
        lines.append(f'  <h2>🛒 Grocery List ({len(profiles)} people)</h2>')
        categories = grocery_list.items_by_category()
        for category, items in sorted(categories.items()):
            cat_display = category.replace("_", " ").title()
            lines.append(f'  <div class="grocery-category">')
            lines.append(f'    <h3>{_escape(cat_display)}</h3>')
            lines.append('    <ul>')
            for item in items:
                qty = round(item.quantity, 1)
                lines.append(
                    f'      <li>{_escape(item.name)}: {qty} {_escape(item.unit)}</li>'
                )
            lines.append('    </ul>')
            lines.append('  </div>')
        lines.append('</section>')

        # Navigation links
        if is_archive:
            lines.append('<div class="archive-link">')
            lines.append('  <a href="../../index.html">← Current Week</a> · ')
            lines.append('  <a href="../../archive.html">Archive</a>')
            lines.append('</div>')
        else:
            lines.append('<div class="archive-link">')
            lines.append('  <a href="archive.html">View Past Weeks →</a>')
            lines.append('</div>')

        lines.append('</main>')
        lines.append('<footer>Generated by Vegan Meal Planner</footer>')

        return "\n".join(lines)

    def _render_recipe_card(
        self, recipe: Recipe, profiles: list[UserProfile], max_target: int
    ) -> str:
        """Render a single recipe as an HTML card.

        Args:
            recipe: The Recipe to render.
            profiles: User profiles for per-person servings.
            max_target: The highest protein target (plan was generated for this).

        Returns:
            HTML string for the recipe card.
        """
        protein = recipe.macros_per_serving.get("protein_g", 0)
        lines: list[str] = []

        lines.append('  <div class="recipe-card">')
        lines.append(f'    <h3>{_escape(recipe.name)}</h3>')

        # Meta info
        lines.append('    <div class="recipe-meta">')
        lines.append(f'      <span>🥜 {protein}g protein/serving</span>')
        if recipe.prep_time_min:
            lines.append(f'      <span>🔪 {recipe.prep_time_min} min prep</span>')
        if recipe.cook_time_min:
            lines.append(f'      <span>🔥 {recipe.cook_time_min} min cook</span>')
        lines.append('    </div>')

        # Per-person servings
        lines.append('    <div class="servings-list">')
        for profile in profiles:
            ratio = profile.protein_target_g / max_target
            person_servings = round(ratio * recipe.servings, 1)
            lines.append(
                f'      <span class="person">'
                f'<strong>{_escape(profile.name)}</strong>: {person_servings} servings'
                f'</span>'
            )
        lines.append('    </div>')

        # Collapsible ingredients
        lines.append('    <details>')
        lines.append('      <summary>Ingredients</summary>')
        lines.append('      <div class="content">')
        lines.append('        <ul>')
        for ing in recipe.ingredients:
            qty = round(ing.quantity, 1)
            lines.append(
                f'          <li>{qty} {_escape(ing.unit)} {_escape(ing.name)}</li>'
            )
        lines.append('        </ul>')
        lines.append('      </div>')
        lines.append('    </details>')

        # Collapsible instructions
        lines.append('    <details>')
        lines.append('      <summary>Instructions</summary>')
        lines.append('      <div class="content">')
        lines.append(
            f'        <div class="instructions">{_escape(recipe.instructions)}</div>'
        )
        lines.append('      </div>')
        lines.append('    </details>')

        lines.append('  </div>')

        return "\n".join(lines)

    def _wrap_html(self, title: str, body: str) -> str:
        """Wrap body content in a full HTML document with embedded CSS.

        Args:
            title: The page title.
            body: The body HTML content.

        Returns:
            Complete HTML document string.
        """
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_escape(title)}</title>
    <style>{EMBEDDED_CSS}</style>
</head>
<body>
{body}
</body>
</html>
"""

    def _git_commit_and_push(self, week_key: str) -> bool:
        """Stage docs/, commit, and push to the remote.

        Args:
            week_key: The YYYY-MM-DD week key for the commit message.

        Returns:
            True if all git operations succeeded, False otherwise.
        """
        try:
            self._run_git(["add", "docs/"])
            # Check if there are staged changes
            result = self._run_git(
                ["diff", "--cached", "--quiet"], check=False
            )
            if result.returncode == 0:
                logger.info("No changes to commit in docs/.")
                return True

            self._run_git(
                ["commit", "-m", f"Update meal plan for week of {week_key}"]
            )
            self._run_git(["push", self.remote_url, "main"])
            logger.info("Pushed meal plan website update for week of %s.", week_key)
            return True

        except subprocess.CalledProcessError as e:
            logger.error(
                "Git operation failed (returncode %d): %s\nstderr: %s",
                e.returncode,
                e.cmd,
                e.stderr,
            )
            return False
        except Exception as e:
            logger.error("Git push failed: %s", e)
            return False

    def _run_git(
        self, args: list[str], check: bool = True
    ) -> subprocess.CompletedProcess:
        """Run a git command in the repo directory.

        Args:
            args: Git command arguments (without 'git' prefix).
            check: Whether to raise on non-zero exit code.

        Returns:
            CompletedProcess result.
        """
        cmd = ["git"] + args
        return subprocess.run(
            cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=check,
            timeout=60,
        )


def _escape(text: str) -> str:
    """Escape HTML special characters.

    Args:
        text: Raw text to escape.

    Returns:
        HTML-escaped text.
    """
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
