#!/usr/bin/env python3
"""
Propose Mind Palace updates based on code analysis.

Phase 5 of Mind Palace: Autonomous Cartography

Compares current code with palace structure and generates proposals
for human review. Proposals can be approved/rejected and then applied.

Usage:
  python scripts/propose_palace_updates.py                    # Analyze and show proposals
  python scripts/propose_palace_updates.py --save proposals.json  # Save for later review
  python scripts/propose_palace_updates.py --apply proposals.json # Apply approved proposals
"""

import sys
import argparse
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.mind_palace import PalaceStorage
from backend.mind_palace.proposals import (
    ProposalManager,
    ProposalStatus,
    save_proposals,
    load_proposals,
)


def main():
    parser = argparse.ArgumentParser(description="Propose Mind Palace updates")
    parser.add_argument("--dir", type=str, default="backend",
                        help="Directory to analyze (default: backend)")
    parser.add_argument("--save", type=str, metavar="FILE",
                        help="Save proposals to JSON file for review")
    parser.add_argument("--apply", type=str, metavar="FILE",
                        help="Apply approved proposals from JSON file")
    parser.add_argument("--approve-all", action="store_true",
                        help="Auto-approve all proposals (use with caution)")
    parser.add_argument("--limit", type=int, default=50,
                        help="Limit number of proposals shown (default: 50)")
    parser.add_argument("--type", type=str,
                        help="Filter by proposal type (add_room, remove_room, update_room, etc.)")
    parser.add_argument("--file", type=str,
                        help="Filter by file pattern (e.g., 'memory' matches files containing 'memory')")
    parser.add_argument("--public-only", action="store_true",
                        help="Only show proposals for public functions (exclude _private)")
    args = parser.parse_args()

    storage = PalaceStorage(PROJECT_ROOT)

    if not storage.exists():
        print("No palace found. Run scripts/rebuild_palace_map.py first.")
        return 1

    palace = storage.load()
    if not palace:
        print("Failed to load palace.")
        return 1

    manager = ProposalManager(palace, storage)

    if args.apply:
        # Load and apply proposals from file
        proposal_file = Path(args.apply)
        if not proposal_file.exists():
            print(f"Proposal file not found: {args.apply}")
            return 1

        proposal_set = load_proposals(proposal_file)
        approved_count = sum(1 for p in proposal_set.proposals
                            if p.status == ProposalStatus.APPROVED)

        print(f"Loaded {len(proposal_set.proposals)} proposals, {approved_count} approved")

        if approved_count == 0:
            print("No approved proposals to apply.")
            print("Edit the JSON file and set 'status': 'approved' for proposals to apply.")
            return 0

        applied = manager.apply_approved(proposal_set)
        print(f"Applied {applied} proposals to palace.")

        # Save updated proposals with applied status
        save_proposals(proposal_set, proposal_file)
        return 0

    # Analyze directory for proposals
    scan_dir = PROJECT_ROOT / args.dir
    print(f"Analyzing {scan_dir} for palace updates...")

    proposal_set = manager.analyze_directory(
        scan_dir,
        PROJECT_ROOT,
        source=f"manual scan of {args.dir}",
    )

    # Apply filters
    filtered = proposal_set.proposals
    if args.type:
        filtered = [p for p in filtered if p.type.value == args.type]
    if args.file:
        filtered = [p for p in filtered
                   if args.file.lower() in p.details.get("file", "").lower()]
    if args.public_only:
        filtered = [p for p in filtered if not p.target.startswith("_")]

    # Replace proposals with filtered set for display
    original_count = len(proposal_set.proposals)
    proposal_set.proposals = filtered

    print(f"\nGenerated {original_count} proposals, showing {len(filtered)} after filters\n")

    if not filtered:
        print("No proposals match the given filters.")
        return 0

    # Auto-approve if requested
    if args.approve_all:
        for p in proposal_set.proposals:
            p.status = ProposalStatus.APPROVED
        print("Auto-approved all proposals.")

    # Show summary
    print(proposal_set.summary())

    # Show detailed proposals (limited)
    shown = 0
    for proposal in proposal_set.proposals:
        if shown >= args.limit:
            remaining = len(proposal_set.proposals) - shown
            print(f"\n... and {remaining} more proposals (use --limit to show more)")
            break

        print(f"\n{'='*60}")
        print(f"ID: {proposal.id}")
        print(f"Type: {proposal.type.value}")
        print(f"Target: {proposal.target}")
        print(f"Reason: {proposal.reason}")
        print(f"Status: {proposal.status.value}")
        if proposal.details:
            print("Details:")
            for key, value in proposal.details.items():
                if value is not None:
                    value_str = str(value)[:80]
                    print(f"  {key}: {value_str}")
        shown += 1

    # Save if requested
    if args.save:
        save_path = Path(args.save)
        save_proposals(proposal_set, save_path)
        print(f"\nProposals saved to: {save_path}")
        print("To apply, review the file, change 'status' to 'approved' for desired proposals,")
        print(f"then run: python scripts/propose_palace_updates.py --apply {args.save}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
