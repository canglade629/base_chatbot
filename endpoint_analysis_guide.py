#!/usr/bin/env python3
"""
Endpoint Analysis Guide
Guide for analyzing Databricks serving endpoint responses
"""

def analyze_response_quality(response_data):
    """Analyze the quality of an endpoint response."""
    print("🔍 RESPONSE QUALITY ANALYSIS")
    print("=" * 50)
    
    if not response_data or "predictions" not in response_data:
        print("❌ Invalid response format")
        return
    
    prediction = response_data["predictions"][0] if response_data["predictions"] else {}
    
    # Extract components
    analysis = prediction.get("analysis", "")
    key_findings = prediction.get("key_findings", [])
    citations = prediction.get("citations", [])
    sources_used = prediction.get("sources_used", 0)
    confidence_score = prediction.get("confidence_score", 0.0)
    processing_time = prediction.get("processing_time", 0.0)
    
    print(f"📊 Basic Metrics:")
    print(f"   Sources used: {sources_used}")
    print(f"   Confidence score: {confidence_score:.3f}")
    print(f"   Processing time: {processing_time:.2f}s")
    print(f"   Analysis length: {len(analysis)} characters")
    print(f"   Key findings: {len(key_findings)}")
    print(f"   Citations: {len(citations)}")
    print()
    
    # Quality Analysis
    quality_score = 0
    issues = []
    recommendations = []
    
    # 1. Analysis Quality (40 points)
    print("📄 Analysis Quality:")
    if analysis:
        if len(analysis) > 500:
            quality_score += 20
            print("   ✅ Good length (>500 chars)")
        elif len(analysis) > 200:
            quality_score += 15
            print("   ⚠️  Moderate length (200-500 chars)")
        else:
            quality_score += 5
            issues.append("Analysis too short")
            print("   ❌ Too short (<200 chars)")
        
        # Check for legal terminology
        legal_terms = ["article", "convention", "chamber", "judgment", "principle", "law", "court", "tribunal"]
        legal_term_count = sum(1 for term in legal_terms if term.lower() in analysis.lower())
        if legal_term_count >= 3:
            quality_score += 20
            print(f"   ✅ Good legal terminology ({legal_term_count} terms)")
        elif legal_term_count >= 1:
            quality_score += 10
            print(f"   ⚠️  Some legal terminology ({legal_term_count} terms)")
        else:
            issues.append("Missing legal terminology")
            print("   ❌ Missing legal terminology")
    else:
        issues.append("No analysis provided")
        print("   ❌ No analysis provided")
    
    # 2. Source Quality (30 points)
    print("\n📚 Source Quality:")
    if sources_used > 0:
        if sources_used >= 5:
            quality_score += 20
            print(f"   ✅ Good source coverage ({sources_used} sources)")
        elif sources_used >= 3:
            quality_score += 15
            print(f"   ⚠️  Moderate source coverage ({sources_used} sources)")
        else:
            quality_score += 10
            issues.append("Insufficient sources")
            print(f"   ❌ Insufficient sources ({sources_used} sources)")
        
        # Check for source diversity
        if "judgment" in analysis.lower() and "geneva" in analysis.lower():
            quality_score += 10
            print("   ✅ Good source diversity (both judgment and Geneva)")
        elif "judgment" in analysis.lower() or "geneva" in analysis.lower():
            quality_score += 5
            print("   ⚠️  Limited source diversity")
        else:
            issues.append("Poor source diversity")
            print("   ❌ Poor source diversity")
    else:
        issues.append("No sources used")
        print("   ❌ No sources used")
    
    # 3. Citation Quality (20 points)
    print("\n🔗 Citation Quality:")
    if citations:
        if len(citations) >= 3:
            quality_score += 15
            print(f"   ✅ Good citation count ({len(citations)} citations)")
        else:
            quality_score += 10
            print(f"   ⚠️  Moderate citation count ({len(citations)} citations)")
        
        # Check citation format
        citation_text = " ".join(citations).lower()
        if "**" in citation_text and "`" in citation_text:
            quality_score += 5
            print("   ✅ Good citation formatting")
        elif "**" in citation_text or "`" in citation_text:
            quality_score += 3
            print("   ⚠️  Partial citation formatting")
        else:
            issues.append("Poor citation formatting")
            print("   ❌ Poor citation formatting")
    else:
        issues.append("No citations provided")
        print("   ❌ No citations provided")
    
    # 4. Key Findings Quality (10 points)
    print("\n🎯 Key Findings Quality:")
    if key_findings:
        if len(key_findings) >= 3:
            quality_score += 10
            print(f"   ✅ Good findings count ({len(key_findings)} findings)")
        else:
            quality_score += 5
            print(f"   ⚠️  Moderate findings count ({len(key_findings)} findings)")
    else:
        issues.append("No key findings")
        print("   ❌ No key findings provided")
    
    # Overall Assessment
    print(f"\n🎯 Overall Quality Score: {quality_score}/100")
    
    if quality_score >= 80:
        print("   ✅ Excellent response quality")
    elif quality_score >= 60:
        print("   ⚠️  Good response quality")
    elif quality_score >= 40:
        print("   ⚠️  Fair response quality")
    else:
        print("   ❌ Poor response quality")
    
    # Issues and Recommendations
    if issues:
        print(f"\n⚠️  Issues Found:")
        for issue in issues:
            print(f"   - {issue}")
    
    # Generate recommendations
    print(f"\n💡 Recommendations:")
    if "Analysis too short" in issues:
        print("   - Increase max_tokens in LLM configuration")
        print("   - Improve prompt engineering for longer responses")
    
    if "Insufficient sources" in issues or "No sources used" in issues:
        print("   - Increase top_k parameter for more sources")
        print("   - Improve retrieval logic and query expansion")
        print("   - Check vector search endpoint connectivity")
    
    if "No citations provided" in issues or "Poor citation formatting" in issues:
        print("   - Enhance citation extraction logic")
        print("   - Improve LLM prompts for better citation formatting")
        print("   - Add post-processing for citation validation")
    
    if "Missing legal terminology" in issues:
        print("   - Improve system prompts with legal domain examples")
        print("   - Add few-shot examples in prompts")
        print("   - Enhance query preprocessing for legal terms")
    
    if "Poor source diversity" in issues:
        print("   - Ensure both judgment and Geneva indexes are being searched")
        print("   - Improve routing logic for balanced source selection")
        print("   - Check index connectivity and data availability")

def check_expected_sources(analysis, expected_sources):
    """Check if expected sources are mentioned in the analysis."""
    print(f"\n🔍 Expected Sources Check:")
    analysis_lower = analysis.lower()
    
    found_sources = []
    missing_sources = []
    
    for source in expected_sources:
        if source.lower() in analysis_lower:
            found_sources.append(source)
        else:
            missing_sources.append(source)
    
    if found_sources:
        print(f"   ✅ Found: {', '.join(found_sources)}")
    if missing_sources:
        print(f"   ❌ Missing: {', '.join(missing_sources)}")
    
    return len(found_sources) / len(expected_sources) if expected_sources else 0

def analyze_legal_accuracy(analysis):
    """Analyze legal accuracy of the response."""
    print(f"\n⚖️  Legal Accuracy Analysis:")
    
    # Check for common legal concepts
    legal_concepts = {
        "international humanitarian law": ["ihl", "international humanitarian law", "geneva convention"],
        "war crimes": ["war crime", "war crimes", "grave breach"],
        "crimes against humanity": ["crimes against humanity", "crimes against humanity"],
        "genocide": ["genocide", "genocidal intent"],
        "command responsibility": ["command responsibility", "superior responsibility", "article 7"],
        "protected persons": ["protected person", "civilian", "prisoner of war"],
        "proportionality": ["proportionality", "proportionate", "excessive"],
        "distinction": ["distinction", "discrimination", "adverse distinction"]
    }
    
    found_concepts = []
    for concept, terms in legal_concepts.items():
        if any(term in analysis.lower() for term in terms):
            found_concepts.append(concept)
    
    print(f"   Legal concepts found: {len(found_concepts)}/{len(legal_concepts)}")
    for concept in found_concepts:
        print(f"   ✅ {concept}")
    
    missing_concepts = set(legal_concepts.keys()) - set(found_concepts)
    if missing_concepts:
        print(f"   Missing concepts: {', '.join(missing_concepts)}")
    
    return len(found_concepts) / len(legal_concepts)

def main():
    """Main function to demonstrate analysis."""
    print("📋 ENDPOINT ANALYSIS GUIDE")
    print("=" * 50)
    print("This guide helps you analyze the quality of your endpoint responses.")
    print("Use the functions in this script to evaluate your test results.")
    print()
    print("Example usage:")
    print("1. Run your endpoint test")
    print("2. Copy the response data")
    print("3. Use analyze_response_quality(response_data)")
    print("4. Check for expected sources and legal accuracy")
    print()
    print("Key metrics to look for:")
    print("- Sources used: 5+ is good")
    print("- Confidence score: 0.7+ is good")
    print("- Analysis length: 500+ characters is good")
    print("- Legal terminology: Should include legal terms")
    print("- Citations: Should be properly formatted")
    print("- Key findings: Should be clear and relevant")

if __name__ == "__main__":
    main()
