"""Build a synthetic integration example outside the production site."""

from scripts.integration import publish_bundle, read


if __name__ == "__main__":
    publish_bundle("data/previews", read("data/examples/course-explorer.json"),
                   read("data/examples/teaching-history.json"),
                   {"gpa": read("data/examples/integration/gpa.json"),
                    "professors": read("data/examples/integration/professors.json"),
                    "verified_occurrences": read("data/examples/integration/verified-links.json")},
                   allow_fixtures=True)
    print("Synthetic preview: data/previews/integration.json; never published to public/.")
