#!/bin/bash
# Publish script for claude-slack

set -e

echo "🚀 Preparing to publish claude-slack to NPM..."

# Check if logged in to npm
if ! npm whoami &>/dev/null; then
    echo "❌ Not logged in to NPM. Please run 'npm login' first."
    exit 1
fi

# Run tests
echo "📋 Running tests..."
npm test

# Check version
CURRENT_VERSION=$(node -p "require('./package.json').version")
echo "📦 Current version: $CURRENT_VERSION"

# Prompt for version bump
echo ""
echo "Select version bump type:"
echo "1) Patch (bug fixes)"
echo "2) Minor (new features)" 
echo "3) Major (breaking changes)"
echo "4) Skip version bump"
read -p "Choice [1-4]: " choice

case $choice in
    1) npm version patch ;;
    2) npm version minor ;;
    3) npm version major ;;
    4) echo "Skipping version bump" ;;
    *) echo "Invalid choice"; exit 1 ;;
esac

NEW_VERSION=$(node -p "require('./package.json').version")
echo "📦 Publishing version: $NEW_VERSION"

# Publish to NPM
echo ""
echo "Publishing to NPM..."
npm publish

echo ""
echo "✅ Successfully published claude-slack v$NEW_VERSION!"
echo ""
echo "Users can now install with:"
echo "  npx claude-slack"
echo ""
echo "Don't forget to:"
echo "  1. Push the version tag: git push --tags"
echo "  2. Create a GitHub release"
echo "  3. Update the documentation"