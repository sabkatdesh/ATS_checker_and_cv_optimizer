# Contributing to CVOptimizer

Thank you for your interest in contributing to CVOptimizer! We welcome contributions from everyone.

## 🤝 How to Contribute

### Reporting Bugs
Found a bug? Please open a GitHub issue with:
- **Title:** Clear description of the bug
- **Description:** What you tried, what happened, what you expected
- **Steps to reproduce:** How to recreate the issue
- **Screenshots:** If applicable
- **Environment:** Python version, OS, browser (if frontend)

Example:
```
Title: ATS scoring returns 0 when CV has no experience

Description: When a user with no work experience uploads a CV, 
the ATS scorer returns 0 instead of calculating education/skills.

Steps:
1. Create profile with no work experience
2. Paste job description
3. Click "Optimize CV"

Expected: Should show ATS score based on education + skills
Actual: Shows 0/100
```

### Suggesting Features
Have an idea? Open a GitHub discussion or issue with:
- **What:** What feature you want
- **Why:** Why it would help
- **How:** How you imagine it working

Example:
```
Feature: Email PDF delivery

Why: Users want to receive optimized CV via email instead of 
downloading from the app.

How: Add email field to profile, send PDF link after optimization.
```

### Submitting Code

#### 1. Fork the Repository
```bash
# Go to github.com/sabkatdesh/cv-optimizer
# Click "Fork"
# Clone your fork
git clone https://github.com/YOUR_USERNAME/cv-optimizer.git
cd cv-optimizer
```

#### 2. Create a Feature Branch
```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

Branch naming convention:
- `feature/add-email-delivery`
- `fix/atp-score-bug`
- `refactor/improve-pdf-generation`
- `docs/update-readme`

#### 3. Make Your Changes
```bash
# Install dependencies
pip install -r requirements.txt

# Make changes to files
# Edit code, add features, fix bugs

# Test locally
python -m uvicorn api:app --reload
streamlit run streamlit_app.py
```

#### 4. Test Your Changes
```bash
# Run existing tests
pytest tests/

# Test specific module
pytest tests/test_ats_checker.py

# Test with coverage
pytest --cov=. tests/
```

#### 5. Commit Your Changes
```bash
# Stage changes
git add .

# Commit with clear message
git commit -m "feat: add email delivery for optimized CVs"
```

Commit message format:
- `feat: add new feature`
- `fix: fix bug in ATS scorer`
- `refactor: improve code quality`
- `docs: update documentation`
- `test: add test cases`
- `chore: update dependencies`

#### 6. Push to Your Fork
```bash
git push origin feature/your-feature-name
```

#### 7. Open a Pull Request
Go to https://github.com/sabkatdesh/cv-optimizer
- Click "Compare & pull request"
- Add PR title and description
- Reference any related issues (#123)
- Click "Create pull request"

PR title example: `feat: add email delivery for optimized CVs`

PR description example:
```
## Description
Added email delivery feature so users can receive optimized CVs via email.

## Changes
- Added email field to user profile
- Created email template for CV delivery
- Added Celery task for async email sending
- Updated API endpoint to trigger email after optimization

## Related Issues
Closes #45

## Testing
- Tested with multiple email addresses
- Verified PDF attachment works
- Tested with both Gmail and Outlook

## Checklist
- [x] Code follows style guidelines
- [x] Self-review done
- [x] Comments added for complex logic
- [x] Documentation updated
- [x] Tests added/updated
- [x] No breaking changes
```

---

## 📋 Code Standards

### Style Guide
- Follow PEP 8 (Python style guide)
- Use meaningful variable names
- Add docstrings to functions
- Keep functions small and focused

### Example:
```python
def compute_ats_score(cv_data: UserCVStructured, jd_data: JobDescriptionStructured) -> float:
    """
    Compute ATS score for a CV against a job description.
    
    Args:
        cv_data: Structured user CV
        jd_data: Structured job description
    
    Returns:
        ATS score (0-100)
    
    Example:
        >>> score = compute_ats_score(cv, jd)
        >>> print(f"Score: {score}")
    """
    # Implementation here
    pass
```

### Type Hints
Always use type hints:
```python
# ✅ Good
def validate_jd(text: str) -> ValidationResult:
    pass

# ❌ Bad
def validate_jd(text):
    pass
```

### Comments
Add comments for complex logic:
```python
# Extract all skills from both hard and soft categories
all_skills = cv.skills.hard_skills + cv.skills.soft_skills + cv.skills.tools

# Match against JD requirements using flexible matching
# (substring + token overlap, not semantic similarity)
matched = [skill for skill in all_skills if flexible_match(skill, jd_requirement)]
```

---

## 🧪 Testing

All new features must include tests.

### Write Tests
```bash
# Create test file
touch tests/test_your_feature.py
```

### Test Structure
```python
import pytest
from your_module import your_function

def test_your_function_success():
    """Test that function works correctly."""
    result = your_function("input")
    assert result == "expected_output"

def test_your_function_error():
    """Test that function handles errors."""
    with pytest.raises(ValueError):
        your_function(invalid_input)

@pytest.mark.parametrize("input,expected", [
    ("case1", "result1"),
    ("case2", "result2"),
])
def test_multiple_cases(input, expected):
    """Test multiple cases."""
    assert your_function(input) == expected
```

### Run Tests
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_your_feature.py

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=.
```

---

## 📚 Documentation

### Update README.md
If your feature adds new functionality, update the README:
- Add to feature list
- Add usage example
- Update architecture diagram if needed

### Add Docstrings
Every function should have a docstring:
```python
def function_name(param1: str, param2: int) -> bool:
    """
    One-line description of what the function does.
    
    Longer description if needed. Explain the logic, edge cases, 
    performance considerations, etc.
    
    Args:
        param1: Description of param1
        param2: Description of param2
    
    Returns:
        Description of return value
    
    Raises:
        ValueError: If param1 is empty
        TypeError: If param2 is not an integer
    
    Example:
        >>> result = function_name("test", 42)
        >>> print(result)
        True
    """
    pass
```

---

## 🚀 Development Workflow

### Setup Development Environment
```bash
# Clone repo
git clone https://github.com/YOUR_USERNAME/cv-optimizer.git
cd cv-optimizer

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install pytest pytest-cov black flake8 mypy

# Run formatter
black .

# Run linter
flake8 .

# Run type checker
mypy .
```

### Run Locally
```bash
# Terminal 1: Backend
python -m uvicorn api:app --reload

# Terminal 2: Frontend
streamlit run streamlit_app.py

# Terminal 3: Tests (optional)
pytest --watch
```

---

## 🔍 Code Review Process

1. **You submit PR** → Automated tests run
2. **We review** → We'll check:
   - Code quality
   - Test coverage
   - Documentation
   - Breaking changes
3. **We comment** → We may suggest changes
4. **You update** → Make requested changes
5. **We approve** → PR gets merged
6. **Deploy** → Changes go live!

### What We Look For
- ✅ Tests included
- ✅ Documentation updated
- ✅ No breaking changes
- ✅ Code follows style guide
- ✅ Clear commit messages
- ✅ Performance improvements noted

---

## 💡 Good First Issues

Looking to get started? Check for issues labeled:
- `good first issue` — Simple, well-defined tasks
- `help wanted` — Things we need community help with
- `documentation` — Doc improvements

---

## 🐛 Bug Fix Workflow

1. **Create issue** describing the bug
2. **Create branch** `fix/bug-description`
3. **Write failing test** that reproduces bug
4. **Fix the bug** in the code
5. **Verify test passes**
6. **Submit PR** with test included

Example:
```bash
# Bug: ATS score returns 0 for experience-less CVs
git checkout -b fix/ats-zero-score-bug

# Write test that fails
# pytest tests/test_ats_checker.py  ← FAILS

# Fix the bug in ats_checker.py

# Run test again
# pytest tests/test_ats_checker.py  ← PASSES

# Commit and push
git commit -m "fix: handle ATS scoring for experience-less CVs"
git push origin fix/ats-zero-score-bug
```

---

## 📞 Questions?

- **GitHub Issues:** For bug reports and features
- **GitHub Discussions:** For questions and ideas
- **Email:** sabkatdesh@gmail.com

---

## 🙏 Thank You!

We appreciate all contributions, whether it's code, bug reports, documentation, or just feedback. 

**Every contribution makes CVOptimizer better!**

---

## 📋 Contributor Covenant

Please note that this project is released with a [Contributor Code of Conduct](CODE_OF_CONDUCT.md). By participating in this project you agree to abide by its terms.

We are committed to providing a welcoming and inclusive environment for all contributors.

---

**Happy contributing! 🚀**
