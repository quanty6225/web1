---
layout: FAQ
monikers:
- o365-21vianet
- o365-worldwide
defaultMoniker: o365-worldwide
versioningType: Ranged
title: Domains Frequently Asked Questions | Microsoft Learn
canonicalUrl: https://learn.microsoft.com/en-us/microsoft-365/admin/setup/domains-faq?view=o365-worldwide
config_moniker_range: =o365-worldwide || =o365-21vianet
summary: >
  <p>This article contains answers to frequently asked questions about domains in Microsoft 365.</p>
feedback_system: Standard
feedback_product_url: https://support.microsoft.com/help/4021566/windows-10-send-feedback-to-microsoft-with-feedback-hub-app
breadcrumb_path: /microsoft-365/breadcrumb/toc.json
recommendations: true
uhfHeaderId: MSDocsHeader-M365-IT
ms.date: 2026-04-29T00:00:00.0000000Z
f1.keywords:
- NOCSH
ms.author: frankroj
author: frankroj
manager: scotv
audience: Admin
ms.topic: faq
ms.service: microsoft-365-business
ms.localizationpriority: medium
ms.collection:
- Tier2
- scotvorg
- M365-subscription-management
- Adm_O365
- Adm_TOC
- operations-pod
ms.custom:
- AdminSurgePortfolio
- okr_smb
- seo-marvel-may2020
- adminvideo
- domains
search.appverid:
- BCS160
- MET150
- MOE150
- BEA160
- GEA150
description: Learn more about domains (onmicrosoft domain and transfer domain) by finding answers to your questions in FAQ.
locale: en-us
document_id: 46a11050-b442-7a48-0d37-9bce8908fc14
document_version_independent_id: 5456e564-2629-cfc2-dfc9-2b7934fcf43a
updated_at: 2026-05-06T18:15:00.0000000Z
original_content_git_url: https://github.com/MicrosoftDocs/microsoft-365-docs-pr/blob/live/microsoft-365/admin/setup/domains-faq.yml
gitcommit: https://github.com/MicrosoftDocs/microsoft-365-docs-pr/blob/1256ec988c6429ef9c84ea2a3c772743bc2e4cac/microsoft-365/admin/setup/domains-faq.yml
git_commit_id: 1256ec988c6429ef9c84ea2a3c772743bc2e4cac
default_moniker: o365-worldwide
site_name: Docs
depot_name: office.Microsoft-365-docs
page_type: faq
toc_rel: ../toc.json
feedback_help_link_type: ''
feedback_help_link_url: ''
asset_id: admin/setup/domains-faq
moniker_range_name: 626dcefb463b053bbc5c86fb8d873ef6
monikers:
- o365-21vianet
- o365-worldwide
item_type: Content
source_path: microsoft-365/admin/setup/domains-faq.yml
cmProducts:
- https://authoring-docs-microsoft.poolparty.biz/devrel/1dd701e0-441f-4b0a-9806-aa47decc4e35
spProducts:
- https://authoring-docs-microsoft.poolparty.biz/devrel/0a2fc935-5977-4aa6-9f55-0be03bd2acb8
platformId: cabe2a04-4de8-ad5f-e38d-f16856244708
---

# Domains Frequently Asked Questions | Microsoft Learn

This article contains answers to frequently asked questions about domains in Microsoft 365.

## What is MX priority?

Mail is delivered to the mail exchange server with the lowest preference number (highest priority), so the MX record you use for mail routing should have the lowest preference number, typically 0 or *High* priority.

- When you create an MX record, most DNS hosting providers require you to set the preference number.
- Some label the box *preference*, and some label it *priority*.
- Some require a number, and some ask you to select *Low*, *Medium*, or *High*.
- If you only have one MX record, any value is fine for priority or preference.
- If you have more than one, make sure the MX record for mail routing is higher priority than the one used for validating that you own the domain.

## How can I validate SPF records for my domain?

It's important that you have or create **only one TXT record for SPF**. If you already have an SPF record, you should append the new Microsoft 365 values to it, rather than create a new one. After you add or update your SPF record for Microsoft Email, use one of the following tools to make sure the syntax is correct:

- [SPF Record Testing Tools](http://www.kitterman.com/spf/validate.html)
- [SPF Surveyor](https://dmarcian.com/spf-survey/)
- [Dig web interface](http://digwebinterface.com/)

## What is a domain name?

A domain is a unique name that appears after the **@** sign in email addresses, and after **www.** in web addresses. It typically takes the form of your organization's name and a standard Internet suffix, such as *yourbusiness.com* or *stateuniversity.edu.*

Using a custom domain like **contoso.com** with Microsoft 365 can help build credibility and recognition for your brand. It might also enhance your email reputation, depending on our email provider reducing the likelihood of your emails being marked as spam.

You can [buy a domain in Microsoft 365 and Microsoft 365 can set it up automatically](../get-help-with-domains/buy-a-domain-name), or you can buy or bring one you already own from a domain registrar.

## Is it possible to connect a domain with Personal or Family offerings?

As a benefit of your Microsoft 365 Family or Microsoft 365 Personal subscription, you can create a personalized email address that is associated with your Outlook.com mailbox, for example, yourname@example.com. At the moment, we only support connecting domains managed by GoDaddy with Outlook.com. For more information, see [Get a personalized email address in Microsoft 365](https://support.microsoft.com/office/get-a-personalized-email-address-in-microsoft-365-75416a58-b225-4c02-8c07-8979403b427b).

## What happens if my DNS provider doesn't support certain record types?

If you manage your own DNS records and your DNS host doesn't support all the DNS records that Microsoft 365 needs, some Microsoft 365 features don't work. We recommend that you transfer your domain to a registrar that supports all required DNS records.

Providers that support all required DNS records:

- Aruba.it
- Cloudflare
- Dynadot
- eNomCentral
- Europe Registry
- GoDaddy
- Hover
- INWX.com
- MyHosting.com
- Name.com
- Nearly Free Speech
- Nettica
- Network Information Center (NIC)
- Network Solutions
- Register.com

## How do I set or change the default domain in Microsoft 365?

You must have at least one custom domain that adds to Microsoft 365 before you can choose a default domain.

::: moniker range="o365-worldwide"

1. In the admin center, go to the **Settings** &gt; [Domains](https://go.microsoft.com/fwlink/p/?linkid=834818) page.

::: moniker-end

::: moniker range="o365-21vianet"

1. In the admin center, go to the **Settings** &gt; [Domains](https://go.microsoft.com/fwlink/p/?linkid=2007048) page.

::: moniker-end

1. On the **Domains** page, select the domain you want to set as the default for new email addresses.
2. Select **Set as default**.

::: moniker range="o365-worldwide"

For information about adding or replacing an onmicrosoft.com domain, see [Add or replace your onmicrosoft.com domain](/en-us/admin/setup/add-or-replace-your-onmicrosoftcom-domain).

::: moniker-end

::: moniker range="o365-21vianet"

You can't change the name of your initial *partner.onmschina.cn* domain.

::: moniker-end

Note

Changing the default domain affects new accounts only. This change doesn't affect user credentials or their access to applications or services. Removing or changing a domain on an account can affect mail, online storage, and sign-in credentials.

## Can I add custom subdomains or multiple domains to Microsoft 365?

Yes. To add subdomains, you must manage your own DNS settings at your registrar's website. If you're letting Microsoft manage your DNS settings with NS records, or if you bought the domain from Microsoft, you can't add subdomains.

Typically, you could add up to 5,000 domains to your Microsoft 365 subscription.

For example, you could add the domains contoso.com and contosomarketing.com, and then add the subdomains `www.contoso.com`, `www.partners.contoso.com`, `www.marketing.partners.contoso.com`, and so on.

When you add a subdomain, the subdomain is automatically verified based on the parent domain that's being verified.

When you add multiple domains to Microsoft 365, you can host any of the services, such as email, on any of the domains you add. \*When you change your email to Microsoft 365 by updating a domain's MX record, ALL email sent to that domain starts coming to Microsoft 365. \*

Note

If you added a contoso.com domain to a Microsoft 365 subscription, you can also add the subdomain xyz.contoso.com to another Microsoft 365 organization. When adding the subdomain, you're prompted to add a TXT record in the DNS hosting provider.

## How do I transfer a domain from Microsoft 365 to another host?

For the procedure to transfer a domain, see [Transfer a domain from Microsoft to another host](../get-help-with-domains/transfer-a-domain-from-microsoft-to-another-host).

## How do I pilot Microsoft 365 from my custom domain?

For the procedure to pilot Microsoft 365 email functionality from a custom domain to a Microsoft 365 mailbox, see [Pilot Microsoft 365 from my custom domain](../misc/pilot-microsoft-365-from-my-custom-domain).

## Why do I have an "onmicrosoft.com" domain?

Microsoft 365 creates a domain for you, like *contoso.onmicrosoft.com*, when you sign up with the service. The user ID that you create when you sign up includes the domain, like *alan@contoso.onmicrosoft.com*.

If you want to have your email look like *alan@contoso.com*, [buy the domain](../get-help-with-domains/buy-a-domain-name). If you already own a domain, follow the steps in [Add your users and domain to Microsoft 365](add-domain).

- **You can replace your onmicrosoft.com domain after sign-up.** While you can't rename or remove an existing onmicrosoft.com domain, you can [create a new one and make it your default onmicrosoft.com domain (your "fallback domain")](add-or-replace-your-onmicrosoftcom-domain). For example, if the initial domain you chose was *fourthcoffee.onmicrosoft.com*, if needed you can create a new onmicrosoft.com domain called *fourthcoffeecorp.onmicrosoft.com* and set it to be your fallback domain.
- **You might not be able to change your SharePoint domain name.** Your SharePoint domain name is based on your onmicrosoft.com domain name. The ability to [change the SharePoint domain name](/en-us/sharepoint/change-your-sharepoint-domain-name) is available for organizations whose total number of SharePoint sites and OneDrive accounts is fewer than 10,000. If you have more sites than 10,000 accounts, a limited invite-based preview is available.
- **You can't remove your onmicrosoft.com domain.** Microsoft 365 needs to keep the onmicrosoft.com domain because it's used behind the scenes for your subscription. However, you don't have to use the domain yourself after you add a custom domain. If you choose to create a new onmicrosoft.com domain, it can't be removed. You're limited to five onmicrosoft.com domains in your Microsoft 365 environment, so make sure to check for spelling and to assess your need if you choose to create a new one.

You can keep using the initial onmicrosoft.com domain even after you add your domain. It still works for email and other services, so it's your choice.

## How do I verify my nonprofit or education status?

1. To start the wizard, select **Setup** in the [admin center](/en-us/admin). (Be sure to sign in to Microsoft 365 first.)
2. To become the admin for your school, select the **Become an admin** option in Microsoft 365.
3. Follow the prompt to add a TXT DNS record at the DNS host website for your domain. Why? Because by signing in at the DNS host and adding a record for your domain, you prove to Microsoft 365 that you own the domain name.
4. After you add the record, you'll go back to the Microsoft 365 portal and confirm that you added it, so Microsoft 365 can check.

Have a nonprofit and want to get Microsoft 365? [Make sure your organization qualifies](https://www.microsoft.com/nonprofits/eligibility) and then sign up for the service.

Want to know more about becoming the admin for your school? [Learn all about it](/en-us/microsoft-365/education/deploy/becoming-an-admin-in-office-365-education).

## How can I create a website for my business?

Watch a [short video: Create your business website](https://learn-video.azurefd.net/vod/player?id=d89ace24-5e06-4858-81bf-512300be5d78) about using a web hosting provider to create a website for your domain.

Microsoft 365 doesn't include a public website for your business. To set one up, consider using a web hosting company like GoDaddy, Wix, or WordPress.

1. Search for a web hosting provider where you can build your website.
2. You might find it easiest to choose the website builder at the same company where your domain name is registered.
3. Design your business website, making sure to include your business logo, business purpose, text, images, and links.
4. To integrate the website with Microsoft 365, you can add your business email to the website and a link to Microsoft Teams, SharePoint, or other collaboration tool.
5. Make sure to connect your website to your domain name, which you're also using for email on Microsoft 365.