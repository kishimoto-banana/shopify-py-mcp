import asyncio
import os
import json
import shopify
import time

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl
import mcp.server.stdio

# Shopify API設定
SHOP_URL = os.environ.get("SHOPIFY_SHOP_URL", "")
API_KEY = os.environ.get("SHOPIFY_API_KEY", "")
API_PASSWORD = os.environ.get("SHOPIFY_API_PASSWORD", "")
API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2025-01")


# Shopify APIの初期化
def initialize_shopify_api():
    shop_url = f"https://{API_KEY}:{API_PASSWORD}@{SHOP_URL}/admin/api/{API_VERSION}"
    shopify.ShopifyResource.set_site(shop_url)


server = Server("shopify-py-mcp")


def get_all_shopify_products(total_limit=None, per_page_limit=250):
    """
    ShopifyAPIライブラリを使用して複数ページにわたる商品一覧を取得する関数

    Parameters:
    total_limit (int): 取得する総商品数（Noneの場合はすべての商品を取得）
    per_page_limit (int): 1回のリクエストあたりの商品数（最大250）

    Returns:
    list: 商品のリスト
    """
    # 1ページあたりの上限を250に制限
    per_page_limit = min(per_page_limit, 250)

    all_products = []
    next_page_url = None

    try:
        while True:
            # 既に十分な商品が取得されているか確認
            if total_limit is not None and len(all_products) >= total_limit:
                break

            # 残りの取得数を計算
            current_limit = per_page_limit
            if total_limit is not None:
                current_limit = min(per_page_limit, total_limit - len(all_products))
                if current_limit <= 0:
                    break

            # 商品一覧の取得
            if next_page_url:
                # next_page_urlからpage_infoを抽出
                page_info = extract_page_info(next_page_url)
                products = shopify.Product.find(
                    limit=current_limit, page_info=page_info
                )
            else:
                products = shopify.Product.find(limit=current_limit)

            # 結果が空の場合は終了
            if not products:
                break

            # 取得した商品を追加
            all_products.extend(products)

            # レスポンスヘッダーからページネーション情報を取得
            response_headers = shopify.ShopifyResource.connection.response.headers
            link_header = response_headers.get("Link", "")

            # 次のページURLを抽出
            next_page_url = extract_next_page_url(link_header)
            if not next_page_url:
                break

            # レート制限を避けるために少し待機
            time.sleep(0.5)

    except Exception as e:
        print(f"エラーが発生しました: {e}")

    # total_limitが指定されている場合、指定した数だけ返す
    if total_limit is not None:
        return all_products[:total_limit]

    return all_products


def extract_next_page_url(link_header):
    """
    Linkヘッダーから次のページのURLを抽出する

    Parameters:
    link_header (str): レスポンスのLinkヘッダー

    Returns:
    str: 次のページのURL（存在しない場合はNone）
    """
    if not link_header:
        return None

    links = link_header.split(",")
    for link in links:
        parts = link.split(";")
        if len(parts) != 2:
            continue

        url = parts[0].strip().strip("<>")
        rel = parts[1].strip()

        if 'rel="next"' in rel:
            return url

    return None


def extract_page_info(next_page_url):
    """
    URLからpage_infoパラメータを抽出する

    Parameters:
    next_page_url (str): 次のページのURL

    Returns:
    str: page_infoパラメータ
    """
    import urllib.parse

    parsed_url = urllib.parse.urlparse(next_page_url)
    query_params = urllib.parse.parse_qs(parsed_url.query)

    if "page_info" in query_params:
        return query_params["page_info"][0]

    return None


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    利用可能なツールのリストを返します。
    各ツールはJSON Schemaを使用して引数を指定します。
    """
    return [
        types.Tool(
            name="list_products",
            description="商品一覧を取得する",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "number",
                        "description": "取得する商品数（最大250）",
                        "minimum": 1,
                        "maximum": 250,
                        "default": 50,
                    },
                },
            },
        ),
        types.Tool(
            name="get_product",
            description="商品の詳細情報を取得する",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "number", "description": "商品ID"}
                },
                "required": ["product_id"],
            },
        ),
        types.Tool(
            name="create_product",
            description="新しい商品を作成する",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "商品名"},
                    "body_html": {
                        "type": "string",
                        "description": "商品の説明（HTML形式）",
                    },
                    "vendor": {"type": "string", "description": "ベンダー名"},
                    "product_type": {"type": "string", "description": "商品タイプ"},
                    "tags": {"type": "string", "description": "タグ（カンマ区切り）"},
                    "status": {
                        "type": "string",
                        "description": "ステータス",
                        "enum": ["active", "draft", "archived"],
                        "default": "active",
                    },
                    "variants": {
                        "type": "array",
                        "description": "バリエーション",
                        "items": {
                            "type": "object",
                            "properties": {
                                "price": {"type": "string", "description": "価格"},
                                "sku": {"type": "string", "description": "SKU"},
                                "inventory_quantity": {
                                    "type": "number",
                                    "description": "在庫数",
                                },
                                "option1": {
                                    "type": "string",
                                    "description": "オプション1の値",
                                },
                                "option2": {
                                    "type": "string",
                                    "description": "オプション2の値",
                                },
                                "option3": {
                                    "type": "string",
                                    "description": "オプション3の値",
                                },
                            },
                            "required": ["price"],
                        },
                    },
                    "options": {
                        "type": "array",
                        "description": "オプション",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "オプション名",
                                },
                                "position": {
                                    "position": "number",
                                    "description": "オプション順番",
                                },
                                "values": {
                                    "type": "array",
                                    "description": "オプション値",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["name", "position", "values"],
                        },
                    },
                    "images": {
                        "type": "array",
                        "description": "画像",
                        "items": {
                            "type": "object",
                            "properties": {
                                "src": {"type": "string", "description": "画像URL"},
                                "alt": {
                                    "type": "string",
                                    "description": "代替テキスト",
                                },
                            },
                            "required": ["src"],
                        },
                    },
                },
                "required": ["title"],
            },
        ),
        types.Tool(
            name="update_product",
            description="商品を更新する",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "number", "description": "商品ID"},
                    "title": {"type": "string", "description": "商品名"},
                    "body_html": {
                        "type": "string",
                        "description": "商品の説明（HTML形式）",
                    },
                    "vendor": {"type": "string", "description": "ベンダー名"},
                    "product_type": {"type": "string", "description": "商品タイプ"},
                    "tags": {"type": "string", "description": "タグ（カンマ区切り）"},
                    "status": {
                        "type": "string",
                        "description": "ステータス",
                        "enum": ["active", "draft", "archived"],
                    },
                    "variants": {
                        "type": "array",
                        "description": "バリエーション",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "number",
                                    "description": "バリエーションID",
                                },
                                "price": {"type": "string", "description": "価格"},
                                "sku": {"type": "string", "description": "SKU"},
                                "inventory_quantity": {
                                    "type": "number",
                                    "description": "在庫数",
                                },
                                "option1": {
                                    "type": "string",
                                    "description": "オプション1の値",
                                },
                                "option2": {
                                    "type": "string",
                                    "description": "オプション2の値",
                                },
                                "option3": {
                                    "type": "string",
                                    "description": "オプション3の値",
                                },
                            },
                        },
                    },
                    "options": {
                        "type": "array",
                        "description": "オプション",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "number", "description": "オプションID"},
                                "name": {
                                    "type": "string",
                                    "description": "オプション名",
                                },
                                "position": {
                                    "position": "number",
                                    "description": "オプション順番",
                                },
                                "values": {
                                    "type": "array",
                                    "description": "オプション値",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["name", "values"],
                        },
                    },
                    "images": {
                        "type": "array",
                        "description": "画像",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "number", "description": "画像ID"},
                                "src": {"type": "string", "description": "画像URL"},
                                "alt": {
                                    "type": "string",
                                    "description": "代替テキスト",
                                },
                            },
                            "required": ["src"],
                        },
                    },
                },
                "required": ["product_id"],
            },
        ),
        types.Tool(
            name="delete_product",
            description="商品を削除する",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "number", "description": "商品ID"}
                },
                "required": ["product_id"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    ツール実行リクエストを処理します。
    """
    try:
        initialize_shopify_api()

        if name == "list_products":
            return await handle_list_products(arguments or {})
        elif name == "get_product":
            return await handle_get_product(arguments or {})
        elif name == "create_product":
            return await handle_create_product(arguments or {})
        elif name == "update_product":
            return await handle_update_product(arguments or {})
        elif name == "delete_product":
            return await handle_delete_product(arguments or {})
        else:
            raise ValueError(f"Unknown tool: {name}")
    except Exception as e:
        return [
            types.TextContent(
                type="text",
                text=f"エラーが発生しました: {str(e)}",
            )
        ]


async def handle_list_products(arguments: dict) -> list[types.TextContent]:
    """商品一覧を取得する"""
    limit = int(arguments.get("limit", 50))
    products = get_all_shopify_products(
        total_limit=limit, per_page_limit=250  # 1回のリクエストで最大250件取得
    )

    result = []
    for product in products:
        result.append(
            {
                "id": product.id,
                "title": product.title,
                "vendor": product.vendor,
                "product_type": product.product_type,
                "created_at": product.created_at,
                "updated_at": product.updated_at,
                "status": product.status,
                "variants_count": len(product.variants),
                "images_count": len(product.images),
            }
        )

    return [
        types.TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False),
        )
    ]


async def handle_get_product(arguments: dict) -> list[types.TextContent]:
    """商品の詳細情報を取得する"""
    product_id = arguments.get("product_id")
    if not product_id:
        raise ValueError("product_id is required")

    product = shopify.Product.find(product_id)

    # 商品情報を整形
    result = {
        "id": product.id,
        "title": product.title,
        "body_html": product.body_html,
        "vendor": product.vendor,
        "product_type": product.product_type,
        "created_at": product.created_at,
        "updated_at": product.updated_at,
        "status": product.status,
        "tags": product.tags,
        "variants": [],
        "options": [],
        "images": [],
    }

    # バリエーション情報
    for variant in product.variants:
        result["variants"].append(
            {
                "id": variant.id,
                "title": variant.title,
                "price": variant.price,
                "sku": variant.sku,
                "inventory_quantity": variant.inventory_quantity,
                "option1": variant.option1,
                "option2": variant.option2,
                "option3": variant.option3,
            }
        )

    # オプション情報
    for option in product.options:
        result["options"].append(
            {"id": option.id, "name": option.name, "values": option.values}
        )

    # 画像情報
    for image in product.images:
        result["images"].append({"id": image.id, "src": image.src, "alt": image.alt})

    return [
        types.TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False),
        )
    ]


async def handle_create_product(arguments: dict) -> list[types.TextContent]:
    """新しい商品を作成する"""
    # 必須パラメータのチェック
    title = arguments.get("title")
    if not title:
        raise ValueError("title is required")

    # 商品オブジェクトの作成
    product = shopify.Product()
    product.title = title

    # オプションパラメータの設定
    if "body_html" in arguments:
        product.body_html = arguments["body_html"]
    if "vendor" in arguments:
        product.vendor = arguments["vendor"]
    if "product_type" in arguments:
        product.product_type = arguments["product_type"]
    if "tags" in arguments:
        product.tags = arguments["tags"]
    if "status" in arguments:
        product.status = arguments["status"]

    # オプションの設定
    if "options" in arguments and arguments["options"]:
        options = []
        for option_data in arguments["options"]:
            option = shopify.Option()
            option.name = option_data["name"]
            option.position = option_data["position"]
            option.values = option_data["values"]
            options.append(option)
        product.options = options

    # バリエーションの設定
    if "variants" in arguments and arguments["variants"]:
        variants = []
        for variant_data in arguments["variants"]:
            variant = shopify.Variant()
            if "price" in variant_data:
                variant.price = variant_data["price"]
            if "sku" in variant_data:
                variant.sku = variant_data["sku"]
            if "inventory_quantity" in variant_data:
                variant.inventory_quantity = variant_data["inventory_quantity"]
            if "option1" in variant_data:
                variant.option1 = variant_data["option1"]
            if "option2" in variant_data:
                variant.option2 = variant_data["option2"]
            if "option3" in variant_data:
                variant.option3 = variant_data["option3"]
            variants.append(variant)
        product.variants = variants

    # 画像の設定
    if "images" in arguments and arguments["images"]:
        for image_data in arguments["images"]:
            image = shopify.Image()
            image.src = image_data["src"]
            if "alt" in image_data:
                image.alt = image_data["alt"]
            product.images.append(image)

    # 商品の保存
    product.save()

    return [
        types.TextContent(
            type="text",
            text=json.dumps(
                {
                    "success": True,
                    "product_id": product.id,
                    "message": f"商品「{product.title}」が作成されました",
                },
                indent=2,
                ensure_ascii=False,
            ),
        )
    ]


async def handle_update_product(arguments: dict) -> list[types.TextContent]:
    """商品を更新する"""
    # 必須パラメータのチェック
    product_id = arguments.get("product_id")
    if not product_id:
        raise ValueError("product_id is required")

    # 商品の取得
    product = shopify.Product.find(product_id)

    # 商品情報の更新
    if "title" in arguments:
        product.title = arguments["title"]
    if "body_html" in arguments:
        product.body_html = arguments["body_html"]
    if "vendor" in arguments:
        product.vendor = arguments["vendor"]
    if "product_type" in arguments:
        product.product_type = arguments["product_type"]
    if "tags" in arguments:
        product.tags = arguments["tags"]
    if "status" in arguments:
        product.status = arguments["status"]

    # バリエーションの更新
    if "variants" in arguments and arguments["variants"]:
        for variant_data in arguments["variants"]:
            # バリエーションIDがある場合は既存のバリエーションを更新
            if "id" in variant_data:
                for variant in product.variants:
                    if variant.id == variant_data["id"]:
                        if "price" in variant_data:
                            variant.price = variant_data["price"]
                        if "sku" in variant_data:
                            variant.sku = variant_data["sku"]
                        if "inventory_quantity" in variant_data:
                            variant.inventory_quantity = variant_data[
                                "inventory_quantity"
                            ]
                        if "option1" in variant_data:
                            variant.option1 = variant_data["option1"]
                        if "option2" in variant_data:
                            variant.option2 = variant_data["option2"]
                        if "option3" in variant_data:
                            variant.option3 = variant_data["option3"]
            # バリエーションIDがない場合は新しいバリエーションを追加
            else:
                variant = shopify.Variant()
                variant.product_id = product.id
                if "price" in variant_data:
                    variant.price = variant_data["price"]
                if "sku" in variant_data:
                    variant.sku = variant_data["sku"]
                if "inventory_quantity" in variant_data:
                    variant.inventory_quantity = variant_data["inventory_quantity"]
                if "option1" in variant_data:
                    variant.option1 = variant_data["option1"]
                if "option2" in variant_data:
                    variant.option2 = variant_data["option2"]
                if "option3" in variant_data:
                    variant.option3 = variant_data["option3"]
                product.variants.append(variant)

    # オプションの更新
    if "options" in arguments and arguments["options"]:
        for option_data in arguments["options"]:
            # オプションIDがある場合は既存のオプションを更新
            if "id" in option_data:
                for option in product.options:
                    if option.id == option_data["id"]:
                        option.name = option_data["name"]
                        option.values = option_data["values"]
            # オプションIDがない場合は新しいオプションを追加
            else:
                option = shopify.Option()
                option.product_id = product.id
                option.name = option_data["name"]
                option.values = option_data["values"]
                product.options.append(option)

    # 画像の更新
    if "images" in arguments and arguments["images"]:
        for image_data in arguments["images"]:
            # 画像IDがある場合は既存の画像を更新
            if "id" in image_data:
                for image in product.images:
                    if image.id == image_data["id"]:
                        image.src = image_data["src"]
                        if "alt" in image_data:
                            image.alt = image_data["alt"]
            # 画像IDがない場合は新しい画像を追加
            else:
                image = shopify.Image()
                image.product_id = product.id
                image.src = image_data["src"]
                if "alt" in image_data:
                    image.alt = image_data["alt"]
                product.images.append(image)

    # 商品の保存
    product.save()

    return [
        types.TextContent(
            type="text",
            text=json.dumps(
                {
                    "success": True,
                    "product_id": product.id,
                    "message": f"商品「{product.title}」が更新されました",
                },
                indent=2,
                ensure_ascii=False,
            ),
        )
    ]


async def handle_delete_product(arguments: dict) -> list[types.TextContent]:
    """商品を削除する"""
    # 必須パラメータのチェック
    product_id = arguments.get("product_id")
    if not product_id:
        raise ValueError("product_id is required")

    # 商品の取得
    product = shopify.Product.find(product_id)

    # 商品名を保存
    product_title = product.title

    # 商品の削除
    product.destroy()

    return [
        types.TextContent(
            type="text",
            text=json.dumps(
                {
                    "success": True,
                    "message": f"商品「{product_title}」が削除されました",
                },
                indent=2,
                ensure_ascii=False,
            ),
        )
    ]


async def main():
    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="shopify-py-mcp",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
