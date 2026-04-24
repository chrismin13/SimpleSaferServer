Always sprinkle comments about things we might forget in a few months, or that might not immediately seem obvious on a first read.

---

Double check about documentation that might be related to whatever you are implementing, along with the related links to the index.html file. You are encouraged to rewrite and refactor the documentation whenever it does not make sense to match the behavior seen in code.

When writing comments and documentation, don't write it assuming the person reading it has seen the previous version of the code or comments. For example don't do something like

# previously this did x
# now it does y

instead just do

# this does x

---

Prefer refactoring code if the end result will mean that the code will be simpler, more effective, and easier to maintain, rather than sticking to existing conventions, even if it means more work in the short term

---

When designing any UI elements, always use the frontend-design and uncodixfy skills. Try to reuse existing UI elements and UI patterns from elsewhere in the system or, if creating new ones, follow the same "Bunker" style. Make better use of the vertical space. Consider how this would be viewed both on desktop and mobile.

---

Consider if anything that you add needs to be removed during the uninstallation by the uninstall.sh script.
