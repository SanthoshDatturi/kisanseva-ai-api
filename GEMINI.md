Always store keys and other sensitive or changing information in a .env file.
Always decouple external services and use dependency injection.

Install the current versions of packages

Always follow best project building/ coding and security practices

Write everything we did so far to PROGRESS.md, ensure to note the approach we're taking, the steps
we've done so far, what worked, what not and the current failure we're working on.

Create an abstraction layer (inputs and outputs) between external services like aws services (loosely coupled module) and core logic of the application, decoupling things so they can be changed if needed later.