# Sample data

Drop these into the app (left panel → **Upload file**) to try the agent.

## `ecommerce_sales.csv`

1,489 e-commerce orders across 2024 (~$2.86M revenue). Built with a gentle
upward trend, a Q4 holiday bump, and regional/segment differences so questions
produce interesting answers and charts.

| Column | Description |
|--------|-------------|
| `order_id` | Unique order id |
| `order_date` | Order date (2024-01-01 → 2024-12-31) |
| `region` | North America · Europe · Asia Pacific · Latin America |
| `country` | Country within the region |
| `channel` | Online · Retail · Partner |
| `customer_segment` | Consumer · SMB · Enterprise |
| `product` | Product name (10 products) |
| `category` | Electronics · Furniture · Stationery · Accessories |
| `units_sold` | Units in the order |
| `unit_price` | Price per unit |
| `discount_pct` | Discount applied (%) |
| `revenue` | Net revenue for the order |

### Questions to try
- Which region has the highest total revenue? Show a bar chart by region.
- What's the monthly revenue trend over 2024? Plot it as a line chart.
- Top 5 products by revenue, and their share of the total.
- Compare average order value across customer segments.
- Does a higher discount correlate with more units sold? Show a scatter plot.
- Which category grew the most from Q1 to Q4?
