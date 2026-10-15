"""Pydantic schemas for LLM Tender Enrichment & Client profiles."""

from typing import List, Optional
from pydantic import BaseModel, Field


class BrandRequirement(BaseModel):
    brand_name: str
    strict_auth_required: bool = True


class ProductRequirement(BaseModel):
    name: str
    category: str = "General"
    quantity: int = 1
    unit: str = "Units"
    requires_oem_or_auth: bool = True


class EnrichedTender(BaseModel):
    id: str
    title: str
    reference_no: str
    ministry_name: str
    department_name: str
    tender_amount: float
    expected_turnover_3yr: float
    min_net_worth: float
    min_solvency: float
    max_ongoing_work_allowed: float = 0.0
    oem_required: bool = False
    min_local_content_class: str = "CLASS-1"
    min_tech_staff: int = 10
    msme_exempt_turnover: bool = False
    status: str = "ACTIVE"
    published_at: int = 0
    deadline_at: int = 0
    scraped_at: Optional[str] = None
    source_portal: Optional[str] = "CPPP"
    listed_date: Optional[str] = None
    tender_url: Optional[str] = None
    region_name: str = "Karnataka"
    region_state_code: str = "KA"
    work_categories: List[str] = Field(default_factory=list)
    specializations: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    brands: List[BrandRequirement] = Field(default_factory=list)
    products: List[ProductRequirement] = Field(default_factory=list)
    enlistment_classes: List[str] = Field(default_factory=list)


class ClientProfile(BaseModel):
    id: str
    name: str
    founded_date: str = "2015-01-01"
    legal_form: str = "PRIVATE_LIMITED"
    turnover_fy24: float = 0.0
    turnover_fy25: float = 0.0
    turnover_fy26: float = 0.0
    avg_turnover_3yr: float = 0.0
    net_worth: float = 0.0
    solvency: float = 0.0
    ongoing_work_value: float = 0.0
    is_msme: bool = False
    is_startup: bool = False
    local_content_class: str = "CLASS-1"
    is_blacklisted: bool = False
    tech_staff_count: int = 10
    portal_seller_id: Optional[str] = None
    work_categories: List[str] = Field(default_factory=list)
    specializations: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    enlistment_classes: List[str] = Field(default_factory=list)
    regions: List[str] = Field(default_factory=list)
