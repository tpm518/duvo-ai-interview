# Remote task

**Instructions:**

- Follow the steps below and implement the task at hand. The steps are laid out as logical extensions and should be implemented in order.
- Your goal is to ship a small but real piece of customer-deployable infrastructure. You could easily spend enormous amount of time on each step, so make sure that you use your time wisely. At each step, identify the core problem, solve it, and move on.
- We want you to make tradeoffs between completeness, polish and architecture in order to deliver the best overall result.
- You are free to use the language and framework of your choice. Please simulate how you'd actually solve this in your job.
- Note: this server is going to run inside a customer's network, not on a public PaaS. Plan accordingly.

**Goal:**

We're going to ship a custom MCP server to a Duvo customer.

**Context:**

Korral is a European specialty grocery chain — ~180 stores, ~18,000 active SKUs. They run a homegrown store-ordering and stock-tracking tool called **StoreLink**. Korral's category buyers spend hours every day in StoreLink doing detective work — checking on-hand vs. POS, deciding whether a store is going to be empty by afternoon, raising replenishment orders. Duvo has just signed a pilot to put an agent on top of this workflow.

Your job is to build the MCP server that lets a Duvo agent talk to StoreLink, and to plan how Duvo will deploy and operate it inside Korral's environment.

**StoreLink API (excerpt):**

```
GET   /v1/stores                                       List stores
GET   /v1/stores/{store_id}                            Store details
GET   /v1/stores/{store_id}/inventory?sku={sku}        Current on-hand for a SKU
GET   /v1/stores/{store_id}/pos?sku={sku}&since=...    Recent POS transactions for a SKU
POST  /v1/stores/{store_id}/replenishment              Raise a replenishment order
GET   /v1/stores/{store_id}/replenishment/{order_id}   Order status
GET   /v1/skus/{sku}                                   SKU details (name, category, supplier)
GET   /v1/suppliers/{supplier_id}                      Supplier details (incl. lead time)
```

Auth: `X-Korral-Store-Key: <key>` header, sent on every request. Each key is scoped to a single store and rotated weekly by Korral's IT.

- Step 1
    
    **The basics**
    
    Build an MCP server that exposes the minimum set of tools a Duvo agent needs to do a buyer's job. Stubbing the StoreLink calls is fine — the integration plumbing isn't what we're testing. What we're testing is the agent-facing surface: which tools you expose, what you choose *not* to expose, what shapes you return, and how you name things. List your decisions briefly in the README.
    
- Step 2
    
    **Doing the job**
    
    Connect your MCP server to an MCP client of your choice (Claude Desktop, Claude Code, custom — whatever you'd reach for). Use it to complete this real buyer task end-to-end:
    
    > "SKU 8847291 (Madeta butter 250g) is running empty at stores 47 and 102. Check on-hand vs. last 24h of POS for both, and raise a replenishment order for any store where the gap exceeds 6 units."
    > 
    
    Show it working in the recording.
    
- Step 3
    
    **Observable**
    
    Add observability. Two people will read your traces: an FDE debugging at 11pm when something is broken, and a Korral category buyer reading the audit log the next morning trying to understand what the agent did on their behalf. Decide what each of them needs and ship it.
    
- Step 4
    
    **Locking it down**
    
    StoreLink uses a per-store API key, rotated weekly by Korral's IT. Your server needs to handle this. Implement secret loading and a story for what happens when (a) a key rotates while a request is in flight, and (b) the agent asks for a store your server doesn't have credentials for. Both should fail safely and informatively — Korral's IT will judge you on both.
    
- Step 5
    
    **Shipping it to Korral**
    
    Write a short `DEPLOYMENT.md` and include a runnable artifact (Dockerfile or equivalent). Korral's IT has told you:
    
    - StoreLink is not reachable from the public internet
    - No customer data may leave Korral's GCP tenancy
    - You will ship updates frequently after go-live
    
    Cover: where this runs, how it gets there, how secrets are handled, who owns the pipeline (Duvo or Korral), how you ship a fix at 11pm if something breaks, and what you'd want to confirm with Korral's IT before day 1.