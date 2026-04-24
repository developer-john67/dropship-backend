# orders/emails.py
"""
Order ticket email utility.
Sends a styled HTML receipt/ticket to the customer after successful payment.
"""

import logging
import uuid
from django.core.mail import EmailMultiAlternatives
from django.conf import settings

logger = logging.getLogger(__name__)


def send_order_ticket(order, order_items):
    """
    Send an order confirmation ticket to the customer.
    Args:
        order:       Order model instance (already saved, payment_status == 'paid')
        order_items: QuerySet / list of OrderItem instances for this order
    """
    customer_email = order.customer_email
    if not customer_email:
        logger.warning(f"[EMAIL] No customer email for order {order.order_number} — skipping ticket")
        return

    customer_name = order.customer_name or "Valued Customer"
    ticket_id = f"TKT-{str(order.order_id).upper()[:8]}"

    #Build item rows
    item_rows_html = ""
    item_rows_text = ""

    for item in order_items:
        unit_price   = float(item.unit_price)
        qty          = item.quantity
        discount     = float(item.discount) if item.discount else 0.0
        line_total   = float(item.total_price)
        discount_html = (
            f'<td style="padding:10px 8px;text-align:center;color:#16a34a;font-size:13px;">'
            f'-${discount:.2f}</td>'
        ) if discount > 0 else (
            '<td style="padding:10px 8px;text-align:center;color:#999;font-size:13px;">—</td>'
        )

        item_rows_html += f"""
        <tr style="border-bottom:1px solid #f0f0f0;">
            <td style="padding:10px 8px;font-size:14px;color:#333;">{item.product_name}</td>
            <td style="padding:10px 8px;text-align:center;font-size:14px;color:#555;">{qty}</td>
            <td style="padding:10px 8px;text-align:right;font-size:14px;color:#333;">${unit_price:.2f}</td>
            {discount_html}
            <td style="padding:10px 8px;text-align:right;font-size:14px;font-weight:600;color:#111;">${line_total:.2f}</td>
        </tr>
        """

        discount_text = f"  Discount: -${discount:.2f}" if discount > 0 else ""
        item_rows_text += (
            f"  {item.product_name}\n"
            f"    Qty: {qty}  |  Unit: ${unit_price:.2f}{discount_text}  |  Total: ${line_total:.2f}\n"
        )

    #Totals
    subtotal        = float(order.subtotal)
    discount_amount = float(order.discount_amount)
    shipping_cost   = float(order.shipping_cost)
    total_amount    = float(order.total_amount)

    discount_row_html = ""
    discount_row_text = ""
    if discount_amount > 0:
        discount_row_html = f"""
        <tr>
            <td colspan="2" style="padding:4px 0;font-size:13px;color:#16a34a;">Discount</td>
            <td style="padding:4px 0;font-size:13px;color:#16a34a;text-align:right;">-${discount_amount:.2f}</td>
        </tr>
        """
        discount_row_text = f"  Discount:   -${discount_amount:.2f}\n"

    shipping_display = "Free" if shipping_cost == 0 else f"${shipping_cost:.2f}"

    #HTML email 
    html_body = f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Order Confirmation – {order.order_number}</title>
</head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:40px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:12px;overflow:hidden;
                    box-shadow:0 4px 24px rgba(0,0,0,0.08);max-width:600px;width:100%;">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#FA7207 0%,#e05e00 100%);
                     padding:36px 40px;text-align:center;">
            <div style="font-size:28px;font-weight:900;color:#fff;letter-spacing:-0.5px;">
              🛍️ Dropship
            </div>
            <div style="color:rgba(255,255,255,0.85);font-size:14px;margin-top:6px;">
              Order Confirmation &amp; Receipt
            </div>
          </td>
        </tr>

        <!-- Ticket ID banner -->
        <tr>
          <td style="background:#fff8f3;border-bottom:2px dashed #FA7207;
                     padding:16px 40px;text-align:center;">
            <span style="font-size:11px;text-transform:uppercase;letter-spacing:1.5px;color:#999;">
              Ticket ID
            </span><br>
            <span style="font-size:22px;font-weight:800;color:#FA7207;letter-spacing:2px;">
              {ticket_id}
            </span>
          </td>
        </tr>

        <!-- Greeting -->
        <tr>
          <td style="padding:32px 40px 20px;">
            <p style="margin:0 0 8px;font-size:20px;font-weight:700;color:#111;">
              Hi {customer_name}! 🎉
            </p>
            <p style="margin:0;font-size:15px;color:#555;line-height:1.6;">
              Your payment was successful and your order is confirmed.
              Here's your receipt — keep it for your records.
            </p>
          </td>
        </tr>

        <!--Order meta -->
        <tr>
          <td style="padding:0 40px 24px;">
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="background:#f9fafb;border-radius:8px;padding:16px;">
              <tr>
                <td style="font-size:13px;color:#888;padding:4px 12px;">Order Number</td>
                <td style="font-size:13px;font-weight:700;color:#111;
                           text-align:right;padding:4px 12px;">{order.order_number}</td>
              </tr>
              <tr>
                <td style="font-size:13px;color:#888;padding:4px 12px;">Payment Method</td>
                <td style="font-size:13px;font-weight:700;color:#111;
                           text-align:right;padding:4px 12px;">{order.payment_method.upper() or 'M-PESA'}</td>
              </tr>
              <tr>
                <td style="font-size:13px;color:#888;padding:4px 12px;">Payment Status</td>
                <td style="text-align:right;padding:4px 12px;">
                  <span style="background:#dcfce7;color:#166534;font-size:12px;
                               font-weight:700;padding:3px 10px;border-radius:20px;">
                    ✓ PAID
                  </span>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Items table -->
        <tr>
          <td style="padding:0 40px 24px;">
            <p style="margin:0 0 12px;font-size:15px;font-weight:700;color:#111;">
              Items Ordered
            </p>
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">
              <thead>
                <tr style="background:#f3f4f6;">
                  <th style="padding:10px 8px;text-align:left;font-size:12px;
                             color:#666;text-transform:uppercase;letter-spacing:0.5px;">Product</th>
                  <th style="padding:10px 8px;text-align:center;font-size:12px;
                             color:#666;text-transform:uppercase;letter-spacing:0.5px;">Qty</th>
                  <th style="padding:10px 8px;text-align:right;font-size:12px;
                             color:#666;text-transform:uppercase;letter-spacing:0.5px;">Unit Price</th>
                  <th style="padding:10px 8px;text-align:center;font-size:12px;
                             color:#666;text-transform:uppercase;letter-spacing:0.5px;">Discount</th>
                  <th style="padding:10px 8px;text-align:right;font-size:12px;
                             color:#666;text-transform:uppercase;letter-spacing:0.5px;">Total</th>
                </tr>
              </thead>
              <tbody>
                {item_rows_html}
              </tbody>
            </table>
          </td>
        </tr>

        <!--Totals-->
        <tr>
          <td style="padding:0 40px 32px;">
            <table width="280" align="right" cellpadding="0" cellspacing="0"
                   style="border-top:2px solid #e5e7eb;">
              <tr>
                <td style="padding:8px 0;font-size:13px;color:#555;">Subtotal</td>
                <td style="padding:8px 0;font-size:13px;color:#555;text-align:right;">${subtotal:.2f}</td>
              </tr>
              {discount_row_html}
              <tr>
                <td style="padding:4px 0;font-size:13px;color:#555;">Shipping</td>
                <td style="padding:4px 0;font-size:13px;color:#555;text-align:right;">{shipping_display}</td>
              </tr>
              <tr style="border-top:2px solid #111;">
                <td style="padding:12px 0 0;font-size:16px;font-weight:800;color:#111;">Total Paid</td>
                <td style="padding:12px 0 0;font-size:16px;font-weight:800;
                           color:#FA7207;text-align:right;">${total_amount:.2f}</td>
              </tr>
            </table>
          </td>
        </tr>

        <!--Footer -->
        <tr>
          <td style="background:#f9fafb;border-top:1px solid #e5e7eb;
                     padding:24px 40px;text-align:center;">
            <p style="margin:0 0 6px;font-size:13px;color:#888;">
              Questions? Reply to this email or visit our Help Center.
            </p>
            <p style="margin:0;font-size:12px;color:#bbb;">
              © Dropship · This is an automated receipt, please do not reply directly.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>
"""

    #Plain-text fallback
    text_body = f"""
ORDER CONFIRMATION — DROPSHIP
==============================
Ticket ID:      {ticket_id}
Order Number:   {order.order_number}
Payment Status: PAID

Hi {customer_name},

Your order has been confirmed and payment received. Here is your receipt:

ITEMS ORDERED
-------------
{item_rows_text}
SUMMARY
-------
  Subtotal:   ${subtotal:.2f}
{discount_row_text}  Shipping:   {shipping_display}
  ─────────────────────
  TOTAL PAID: ${total_amount:.2f}

Payment Method: {order.payment_method.upper() or 'M-PESA'}

Thank you for shopping with Dropship!
"""

    #Send
    subject = f"Order Confirmed — {order.order_number} | Dropship"
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@dropship.com')

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=from_email,
            to=[customer_email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"[EMAIL] Ticket sent to {customer_email} for order {order.order_number}")
    except Exception as exc:
        logger.error(f"[EMAIL] Failed to send ticket for order {order.order_number}: {exc}")